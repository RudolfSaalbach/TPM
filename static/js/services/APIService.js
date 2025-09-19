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
     * Execute HTTP request with retry logic
     */
    async request(endpoint, options = {}) {
        const requestId = ++this.requestId;
        const url = this.buildURL(endpoint, options.params);

        this.activeRequests.set(requestId, { endpoint, options, startTime: Date.now() });

        try {
            this.eventBus?.emit('api:requestStart', { requestId, endpoint, options });

            const config = this.createRequestConfig(endpoint, options);
            const response = await this.executeWithRetry(url, config, requestId);

            // Apply response interceptors
            const processedResponse = this.responseInterceptors.reduce((resp, interceptor) => {
                return interceptor(resp) || resp;
            }, response);

            this.eventBus?.emit('api:requestSuccess', {
                requestId,
                endpoint,
                response: processedResponse,
                duration: Date.now() - this.activeRequests.get(requestId).startTime
            });

            return processedResponse;

        } catch (error) {
            this.eventBus?.emit('api:requestError', {
                requestId,
                endpoint,
                error,
                duration: Date.now() - this.activeRequests.get(requestId).startTime
            });

            throw error;
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

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ChronosAPIService, APIError };
}