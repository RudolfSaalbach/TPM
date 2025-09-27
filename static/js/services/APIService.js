/**
 * APIService - Centralized API communication service
 * Separates API logic from UI components
 */
class ChronosAPIService {
    constructor(options = {}) {
        this.baseURL = options.baseURL || '/api/v1';
        this.apiKey = options.apiKey || this.getStoredAPIKey();
        this.timeout = options.timeout || 30000;
        this.retryAttempts = options.retryAttempts || 3;
        this.retryDelay = options.retryDelay || 1000;

        // Request interceptors
        this.requestInterceptors = [];
        this.responseInterceptors = [];

        // Event bus for API events
        this.eventBus = window.ChronosEventBus;

        // Active requests tracking
        this.activeRequests = new Map();
        this.requestId = 0;

        // Circuit breaker for API resilience
        this.circuitBreaker = new CircuitBreaker({
            failureThreshold: options.failureThreshold || 5,
            resetTimeout: options.resetTimeout || 60000,
            monitoringPeriod: options.monitoringPeriod || 10000
        });

        // Error statistics and monitoring
        this.errorStats = {
            totalRequests: 0,
            totalErrors: 0,
            networkErrors: 0,
            serverErrors: 0,
            clientErrors: 0,
            lastErrorTime: null,
            recentErrors: [] // Last 10 errors
        };

        // Connection state management
        this.connectionState = {
            isOnline: navigator.onLine || true,
            lastSuccessfulRequest: Date.now(),
            consecutiveFailures: 0,
            backoffDelay: 1000
        };

        // Request queue for offline scenarios
        this.requestQueue = [];
        this.maxQueueSize = options.maxQueueSize || 50;

        // Set up network monitoring
        this.setupNetworkMonitoring();
    }

    /**
     * Get stored API key from localStorage
     */
    getStoredAPIKey() {
        return localStorage.getItem('chronos_api_key') || '';
    }

    /**
     * Set API key and store it
     */
    setAPIKey(apiKey) {
        this.apiKey = apiKey;
        localStorage.setItem('chronos_api_key', apiKey);
        this.eventBus?.emit('api:keyChanged', apiKey);
    }

    /**
     * Get auth headers
     */
    getAuthHeaders() {
        const headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        };

        if (this.apiKey) {
            headers['Authorization'] = `Bearer ${this.apiKey}`;
        }

        return headers;
    }

    /**
     * Add request interceptor
     */
    addRequestInterceptor(interceptor) {
        this.requestInterceptors.push(interceptor);
    }

    /**
     * Add response interceptor
     */
    addResponseInterceptor(interceptor) {
        this.responseInterceptors.push(interceptor);
    }

    /**
     * Create request configuration
     */
    createRequestConfig(endpoint, options = {}) {
        const config = {
            method: options.method || 'GET',
            headers: {
                ...this.getAuthHeaders(),
                ...options.headers
            },
            timeout: options.timeout || this.timeout,
            ...options
        };

        // Add body for non-GET requests
        if (options.body && config.method !== 'GET') {
            config.body = typeof options.body === 'string'
                ? options.body
                : JSON.stringify(options.body);
        }

        // Apply request interceptors
        return this.requestInterceptors.reduce((conf, interceptor) => {
            return interceptor(conf) || conf;
        }, config);
    }

    /**
     * Set up network monitoring
     */
    setupNetworkMonitoring() {
        window.addEventListener('online', () => {
            this.connectionState.isOnline = true;
            this.connectionState.consecutiveFailures = 0;
            this.connectionState.backoffDelay = 1000;
            this.eventBus?.emit('api:connectionRestored');
            this.processRequestQueue();
        });

        window.addEventListener('offline', () => {
            this.connectionState.isOnline = false;
            this.eventBus?.emit('api:connectionLost');
        });
    }

    /**
     * Execute HTTP request with enhanced error handling
     */
    async request(endpoint, options = {}) {
        const requestId = ++this.requestId;
        const url = this.buildURL(endpoint, options.params);

        // Check circuit breaker
        if (this.circuitBreaker.isOpen()) {
            throw new APIError('Service temporarily unavailable (circuit breaker open)', 503, {
                type: 'circuit_breaker',
                nextRetryTime: this.circuitBreaker.nextRetryTime()
            });
        }

        // Check if we're offline and should queue the request
        if (!this.connectionState.isOnline && options.queueWhenOffline !== false) {
            return this.queueRequest(endpoint, options);
        }

        this.activeRequests.set(requestId, { endpoint, options, startTime: Date.now() });
        this.errorStats.totalRequests++;

        try {
            this.eventBus?.emit('api:requestStart', { requestId, endpoint, options });

            const config = this.createRequestConfig(endpoint, options);
            const response = await this.executeWithRetry(url, config, requestId);

            // Apply response interceptors
            const processedResponse = this.responseInterceptors.reduce((resp, interceptor) => {
                return interceptor(resp) || resp;
            }, response);

            // Record successful request
            this.recordSuccessfulRequest();

            this.eventBus?.emit('api:requestSuccess', {
                requestId,
                endpoint,
                response: processedResponse,
                duration: Date.now() - this.activeRequests.get(requestId).startTime
            });

            return processedResponse;

        } catch (error) {
            // Record failed request
            this.recordFailedRequest(error);

            this.eventBus?.emit('api:requestError', {
                requestId,
                endpoint,
                error,
                duration: Date.now() - this.activeRequests.get(requestId).startTime
            });

            // Enhanced error handling
            throw this.enhanceError(error, endpoint, options);
        } finally {
            this.activeRequests.delete(requestId);
        }
    }

    /**
     * Execute request with retry logic
     */
    async executeWithRetry(url, config, requestId, attempt = 1) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), config.timeout);

            const response = await fetch(url, {
                ...config,
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new APIError(`HTTP ${response.status}`, response.status, await this.parseErrorResponse(response));
            }

            return await this.parseResponse(response);

        } catch (error) {
            // Don't retry on certain errors
            if (error instanceof APIError && error.status >= 400 && error.status < 500) {
                throw error;
            }

            // Retry logic
            if (attempt < this.retryAttempts) {
                this.eventBus?.emit('api:requestRetry', { requestId, attempt, error });

                await this.delay(this.retryDelay * attempt);
                return this.executeWithRetry(url, config, requestId, attempt + 1);
            }

            throw error;
        }
    }

    /**
     * Parse response based on content type
     */
    async parseResponse(response) {
        const contentType = response.headers.get('content-type') || '';

        if (contentType.includes('application/json')) {
            return await response.json();
        }

        if (contentType.includes('text/')) {
            return await response.text();
        }

        if (contentType.includes('application/octet-stream')) {
            return await response.blob();
        }

        return response;
    }

    /**
     * Parse error response
     */
    async parseErrorResponse(response) {
        try {
            const contentType = response.headers.get('content-type') || '';
            if (contentType.includes('application/json')) {
                return await response.json();
            }
            return await response.text();
        } catch {
            return null;
        }
    }

    /**
     * Build URL with parameters
     */
    buildURL(endpoint, params = {}) {
        const url = new URL(endpoint.startsWith('http') ? endpoint : this.baseURL + endpoint, window.location.origin);

        Object.entries(params).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') {
                url.searchParams.append(key, String(value));
            }
        });

        return url.toString();
    }

    /**
     * Delay utility for retries
     */
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // HTTP Methods

    /**
     * GET request
     */
    async get(endpoint, params = {}, options = {}) {
        return this.request(endpoint, {
            ...options,
            method: 'GET',
            params
        });
    }

    /**
     * POST request
     */
    async post(endpoint, body = null, options = {}) {
        return this.request(endpoint, {
            ...options,
            method: 'POST',
            body
        });
    }

    /**
     * PUT request
     */
    async put(endpoint, body = null, options = {}) {
        return this.request(endpoint, {
            ...options,
            method: 'PUT',
            body
        });
    }

    /**
     * PATCH request
     */
    async patch(endpoint, body = null, options = {}) {
        return this.request(endpoint, {
            ...options,
            method: 'PATCH',
            body
        });
    }

    /**
     * DELETE request
     */
    async delete(endpoint, options = {}) {
        return this.request(endpoint, {
            ...options,
            method: 'DELETE'
        });
    }

    // Domain-specific API methods

    /**
     * Events API
     */
    events = {
        list: (params = {}) => this.get('/events', params),
        get: (id) => this.get(`/events/${id}`),
        create: (event) => this.post('/events', event),
        update: (id, event) => this.put(`/events/${id}`, event),
        delete: (id) => this.delete(`/events/${id}`),

        // v2.2 Sub-tasks
        getSubTasks: (eventId) => this.get(`/v2.2/events/${eventId}/sub-tasks`),
        addSubTask: (eventId, subTask) => this.post(`/v2.2/events/${eventId}/sub-tasks`, subTask),
        updateSubTask: (eventId, taskId, subTask) => this.put(`/v2.2/events/${eventId}/sub-tasks/${taskId}`, subTask),
        deleteSubTask: (eventId, taskId) => this.delete(`/v2.2/events/${eventId}/sub-tasks/${taskId}`)
    };

    /**
     * Templates API
     */
    templates = {
        list: (params = {}) => this.get('/templates', params),
        get: (id) => this.get(`/templates/${id}`),
        create: (template) => this.post('/templates', template),
        update: (id, template) => this.put(`/templates/${id}`, template),
        delete: (id) => this.delete(`/templates/${id}`),
        use: (id) => this.post(`/templates/${id}/use`)
    };

    /**
     * Event Links API (v2.2)
     */
    eventLinks = {
        list: (params = {}) => this.get('/v2.2/event-links', params),
        create: (link) => this.post('/v2.2/event-links', link),
        delete: (id) => this.delete(`/v2.2/event-links/${id}`)
    };

    /**
     * Workflows API (v2.2)
     */
    workflows = {
        list: () => this.get('/v2.2/workflows'),
        create: (workflow) => this.post('/v2.2/workflows', workflow),
        delete: (id) => this.delete(`/v2.2/workflows/${id}`)
    };

    /**
     * Availability API (v2.2)
     */
    availability = {
        check: (request) => this.post('/v2.2/availability/check', request),
        findSlots: (request) => this.post('/v2.2/availability/free-slots', request)
    };

    /**
     * Commands API (v2.2)
     */
    commands = {
        poll: (systemName) => this.get(`/v2.2/commands/poll/${systemName}`),
        complete: (commandId, result) => this.post(`/v2.2/commands/${commandId}/complete`, result),
        failed: (commandId, error) => this.post(`/v2.2/commands/${commandId}/failed`, error)
    };

    /**
     * Calendar sync API
     */
    sync = {
        calendar: (options = {}) => this.post('/sync/calendar', options),
        status: () => this.get('/sync/status')
    };

    /**
     * System API
     */
    system = {
        health: () => this.get('/health'),
        status: () => this.get('/status'),
        metrics: () => this.get('/metrics')
    };

    /**
     * Analytics API
     */
    analytics = {
        report: (params = {}) => this.get('/analytics/report', params),
        productivity: (params = {}) => this.get('/analytics/productivity', params),
        insights: (params = {}) => this.get('/analytics/insights', params)
    };

    /**
     * AI Features API
     */
    ai = {
        optimize: (options = {}) => this.post('/ai/optimize', options),
        suggest: (options = {}) => this.post('/ai/suggest', options),
        detect: (options = {}) => this.post('/ai/detect-conflicts', options)
    };

    /**
     * Cancel all active requests
     */
    cancelAllRequests() {
        const count = this.activeRequests.size;
        this.activeRequests.clear();
        this.eventBus?.emit('api:requestsCancelled', { count });
    }

    /**
     * Get active requests info
     */
    getActiveRequests() {
        return Array.from(this.activeRequests.entries()).map(([id, request]) => ({
            id,
            endpoint: request.endpoint,
            duration: Date.now() - request.startTime
        }));
    }

    /**
     * Check if API is available
     */
    async checkHealth() {
        try {
            await this.system.health();
            return true;
        } catch {
            return false;
        }
    }

    /**
     * Batch multiple requests
     */
    async batch(requests) {
        const results = await Promise.allSettled(
            requests.map(({ method, endpoint, ...options }) => {
                return this[method](endpoint, ...Object.values(options));
            })
        );

        return results.map((result, index) => ({
            request: requests[index],
            success: result.status === 'fulfilled',
            data: result.status === 'fulfilled' ? result.value : null,
            error: result.status === 'rejected' ? result.reason : null
        }));
    }

    // Enhanced Error Handling Methods

    /**
     * Record successful request
     */
    recordSuccessfulRequest() {
        this.connectionState.lastSuccessfulRequest = Date.now();
        this.connectionState.consecutiveFailures = 0;
        this.connectionState.backoffDelay = 1000;
        this.circuitBreaker.recordSuccess();
    }

    /**
     * Record failed request
     */
    recordFailedRequest(error) {
        this.errorStats.totalErrors++;
        this.errorStats.lastErrorTime = Date.now();
        this.connectionState.consecutiveFailures++;

        // Categorize error
        if (error instanceof APIError) {
            if (error.isNetworkError) {
                this.errorStats.networkErrors++;
            } else if (error.isServerError) {
                this.errorStats.serverErrors++;
            } else if (error.isClientError) {
                this.errorStats.clientErrors++;
            }
        }

        // Add to recent errors (keep last 10)
        this.errorStats.recentErrors.unshift({
            timestamp: Date.now(),
            error: error.message,
            status: error.status || 0,
            type: this.getErrorType(error)
        });

        if (this.errorStats.recentErrors.length > 10) {
            this.errorStats.recentErrors.pop();
        }

        // Update circuit breaker
        this.circuitBreaker.recordFailure();

        // Increase backoff delay
        this.connectionState.backoffDelay = Math.min(
            this.connectionState.backoffDelay * 2,
            30000 // Max 30 seconds
        );
    }

    /**
     * Enhance error with additional context
     */
    enhanceError(error, endpoint, options) {
        if (error instanceof APIError) {
            error.endpoint = endpoint;
            error.timestamp = Date.now();
            error.consecutiveFailures = this.connectionState.consecutiveFailures;
            error.isRetryable = this.isRetryableError(error);
            error.suggestion = this.getErrorSuggestion(error);
        }

        return error;
    }

    /**
     * Get error type string
     */
    getErrorType(error) {
        if (error instanceof APIError) {
            if (error.isNetworkError) return 'network';
            if (error.isServerError) return 'server';
            if (error.isClientError) return 'client';
        }
        return 'unknown';
    }

    /**
     * Check if error is retryable
     */
    isRetryableError(error) {
        if (error instanceof APIError) {
            // Don't retry client errors (400-499) except for timeout and rate limiting
            if (error.status >= 400 && error.status < 500) {
                return error.status === 408 || error.status === 429;
            }
            // Retry network errors and server errors
            return error.isNetworkError || error.isServerError;
        }
        return true;
    }

    /**
     * Get error suggestion for user
     */
    getErrorSuggestion(error) {
        if (!this.connectionState.isOnline) {
            return 'Check your internet connection';
        }

        if (error instanceof APIError) {
            switch (error.status) {
                case 401:
                    return 'Please check your API key or login again';
                case 403:
                    return 'You do not have permission for this action';
                case 404:
                    return 'The requested resource was not found';
                case 408:
                    return 'Request timeout - please try again';
                case 429:
                    return 'Too many requests - please wait and try again';
                case 500:
                    return 'Server error - please try again later';
                case 503:
                    return 'Service temporarily unavailable - please try again later';
                default:
                    if (error.isNetworkError) {
                        return 'Network error - please check your connection';
                    }
                    return 'An unexpected error occurred - please try again';
            }
        }

        return 'Please try again or contact support if the problem persists';
    }

    /**
     * Queue request for offline scenario
     */
    async queueRequest(endpoint, options) {
        if (this.requestQueue.length >= this.maxQueueSize) {
            // Remove oldest request
            this.requestQueue.shift();
        }

        const queuedRequest = {
            id: this.generateId(),
            endpoint,
            options,
            timestamp: Date.now(),
            attempts: 0
        };

        this.requestQueue.push(queuedRequest);

        this.eventBus?.emit('api:requestQueued', {
            requestId: queuedRequest.id,
            queueSize: this.requestQueue.length
        });

        // Return a promise that resolves when the request is processed
        return new Promise((resolve, reject) => {
            queuedRequest.resolve = resolve;
            queuedRequest.reject = reject;
        });
    }

    /**
     * Process queued requests when connection is restored
     */
    async processRequestQueue() {
        if (this.requestQueue.length === 0) return;

        this.eventBus?.emit('api:processingQueue', { queueSize: this.requestQueue.length });

        const queue = [...this.requestQueue];
        this.requestQueue = [];

        for (const queuedRequest of queue) {
            try {
                const response = await this.request(queuedRequest.endpoint, {
                    ...queuedRequest.options,
                    queueWhenOffline: false
                });

                queuedRequest.resolve?.(response);
            } catch (error) {
                queuedRequest.reject?.(error);
            }
        }

        this.eventBus?.emit('api:queueProcessed', { processedCount: queue.length });
    }

    /**
     * Get comprehensive error statistics
     */
    getErrorStats() {
        const errorRate = this.errorStats.totalRequests > 0
            ? (this.errorStats.totalErrors / this.errorStats.totalRequests) * 100
            : 0;

        return {
            ...this.errorStats,
            errorRate: Math.round(errorRate * 100) / 100,
            connectionState: this.connectionState,
            circuitBreakerState: this.circuitBreaker.getState(),
            queueSize: this.requestQueue.length
        };
    }

    /**
     * Reset error statistics
     */
    resetErrorStats() {
        this.errorStats = {
            totalRequests: 0,
            totalErrors: 0,
            networkErrors: 0,
            serverErrors: 0,
            clientErrors: 0,
            lastErrorTime: null,
            recentErrors: []
        };

        this.circuitBreaker.reset();
    }

    /**
     * Generate unique ID
     */
    generateId() {
        return `api_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }
}

/**
 * Circuit Breaker for API resilience
 */
class CircuitBreaker {
    constructor(options = {}) {
        this.failureThreshold = options.failureThreshold || 5;
        this.resetTimeout = options.resetTimeout || 60000;
        this.monitoringPeriod = options.monitoringPeriod || 10000;

        this.state = 'CLOSED'; // CLOSED, OPEN, HALF_OPEN
        this.failureCount = 0;
        this.lastFailureTime = null;
        this.nextRetryTime = null;
    }

    recordSuccess() {
        this.failureCount = 0;
        this.lastFailureTime = null;
        this.nextRetryTime = null;
        this.state = 'CLOSED';
    }

    recordFailure() {
        this.failureCount++;
        this.lastFailureTime = Date.now();

        if (this.failureCount >= this.failureThreshold) {
            this.state = 'OPEN';
            this.nextRetryTime = Date.now() + this.resetTimeout;
        }
    }

    isOpen() {
        if (this.state === 'OPEN') {
            if (Date.now() >= this.nextRetryTime) {
                this.state = 'HALF_OPEN';
                return false;
            }
            return true;
        }
        return false;
    }

    getState() {
        return {
            state: this.state,
            failureCount: this.failureCount,
            lastFailureTime: this.lastFailureTime,
            nextRetryTime: this.nextRetryTime
        };
    }

    reset() {
        this.state = 'CLOSED';
        this.failureCount = 0;
        this.lastFailureTime = null;
        this.nextRetryTime = null;
    }
}

/**
 * API Error class
 */
class APIError extends Error {
    constructor(message, status = 500, details = null) {
        super(message);
        this.name = 'APIError';
        this.status = status;
        this.details = details;
    }

    get isClientError() {
        return this.status >= 400 && this.status < 500;
    }

    get isServerError() {
        return this.status >= 500;
    }

    get isNetworkError() {
        return this.status === 0 || this.message.includes('network') || this.message.includes('timeout');
    }
}

// Create global API service instance
const globalAPIConfig = {
    baseURL: localStorage.getItem('chronos_api_base') || '/api/v1',
    apiKey: localStorage.getItem('chronos_api_key') || '',
    timeout: 30000,
    retryAttempts: 3
};

window.ChronosAPI = window.ChronosAPI || new ChronosAPIService(globalAPIConfig);

// Export classes
window.ChronosAPIService = ChronosAPIService;
window.APIError = APIError;
window.CircuitBreaker = CircuitBreaker;

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ChronosAPIService, APIError, CircuitBreaker };
}