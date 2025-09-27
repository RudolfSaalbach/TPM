/**
 * StateManager - Centralized state management for Chronos application
 * Implements observable state pattern with persistence
 */
class ChronosStateManager {
    constructor(options = {}) {
        this.options = {
            persistence: true,
            storageKey: 'chronos_app_state',
            debounceDelay: 500,
            maxHistorySize: 50,
            ...options
        };

        // State storage
        this.state = {};
        this.initialState = {};

        // Subscribers for state changes
        this.subscribers = new Map();
        this.globalSubscribers = new Set();

        // State history for undo/redo
        this.history = [];
        this.historyIndex = -1;

        // Computed properties
        this.computed = new Map();
        this.computedCache = new Map();

        // Middleware
        this.middleware = [];

        // Event bus
        this.eventBus = window.ChronosEventBus;

        // API integration
        this.apiService = window.ChronosAPIService;
        this.pendingRequests = new Map();
        this.requestQueue = [];

        // UI bindings
        this.domBindings = new Map();
        this.formBindings = new Map();

        // Sync management
        this.syncInterval = null;
        this.lastServerSync = null;

        // Debounced persistence
        this.debouncedPersist = this.debounce(
            this.persistState.bind(this),
            this.options.debounceDelay
        );

        // Debounced sync
        this.debouncedSync = this.debounce(
            this.syncWithServer.bind(this),
            1000
        );

        this.initialize();
    }

    /**
     * Initialize state manager
     */
    initialize() {
        // Load persisted state
        if (this.options.persistence) {
            this.loadPersistedState();
        }

        // Set up default state if empty
        if (Object.keys(this.state).length === 0) {
            this.state = this.getDefaultState();
        }

        this.initialState = this.deepClone(this.state);

        // Add to history
        this.addToHistory(this.state, 'INIT');

        this.debug('StateManager initialized', this.state);

        // Start automatic sync if enabled
        if (this.get('user.settings.autoSync')) {
            this.startAutoSync();
        }

        // Set up UI bindings observer
        this.setupUIObserver();
    }

    /**
     * Get default application state
     */
    getDefaultState() {
        return {
            // UI State
            ui: {
                theme: 'dark',
                language: 'de',
                sidebarCollapsed: false,
                loading: false,
                error: null,
                notifications: []
            },

            // User State
            user: {
                preferences: {
                    timezone: 'Europe/Berlin',
                    dateFormat: 'DD.MM.YYYY',
                    timeFormat: '24h',
                    defaultCalendar: 'primary'
                },
                settings: {
                    autoSync: true,
                    syncInterval: 300000, // 5 minutes
                    notifications: true,
                    soundEnabled: false
                }
            },

            // Application Data
            data: {
                events: [],
                templates: [],
                calendars: ['primary'],
                filters: {
                    range: '7',
                    direction: 'future',
                    searchQuery: '',
                    calendar: 'primary'
                },
                selectedEvent: null,
                selectedTemplate: null
            },

            // System State
            system: {
                online: true,
                syncStatus: 'idle',
                lastSync: null,
                apiConnected: true,
                activeRequests: 0
            },

            // Feature flags
            features: {
                v22Enabled: true,
                subTasksEnabled: true,
                workflowsEnabled: true,
                aiEnabled: false
            }
        };
    }

    /**
     * Subscribe to state changes
     */
    subscribe(path, callback, options = {}) {
        if (typeof path === 'function') {
            // Global subscriber
            this.globalSubscribers.add(path);
            return () => this.globalSubscribers.delete(path);
        }

        // Path-specific subscriber
        if (!this.subscribers.has(path)) {
            this.subscribers.set(path, new Set());
        }

        const subscriber = {
            callback,
            options: {
                immediate: false,
                deep: false,
                ...options
            },
            id: this.generateId()
        };

        this.subscribers.get(path).add(subscriber);

        // Call immediately if requested
        if (subscriber.options.immediate) {
            const currentValue = this.get(path);
            callback(currentValue, undefined, path);
        }

        // Return unsubscribe function
        return () => {
            const pathSubscribers = this.subscribers.get(path);
            if (pathSubscribers) {
                pathSubscribers.delete(subscriber);
                if (pathSubscribers.size === 0) {
                    this.subscribers.delete(path);
                }
            }
        };
    }

    /**
     * Get state value by path
     */
    get(path) {
        if (!path) return this.state;

        return path.split('.').reduce((obj, key) => {
            return obj && obj[key] !== undefined ? obj[key] : undefined;
        }, this.state);
    }

    /**
     * Set state value by path
     */
    set(path, value, meta = {}) {
        if (typeof path === 'object') {
            // Batch update
            return this.batch(path);
        }

        const oldValue = this.get(path);

        // Apply middleware
        const processedValue = this.applyMiddleware('SET', path, value, oldValue);

        // Update state
        const newState = this.deepClone(this.state);
        this.setNestedValue(newState, path, processedValue);

        this.updateState(newState, {
            type: 'SET',
            path,
            value: processedValue,
            oldValue,
            ...meta
        });

        return processedValue;
    }

    /**
     * Update multiple state values
     */
    batch(updates) {
        const changes = [];
        const newState = this.deepClone(this.state);

        Object.entries(updates).forEach(([path, value]) => {
            const oldValue = this.get(path);
            const processedValue = this.applyMiddleware('BATCH_SET', path, value, oldValue);

            this.setNestedValue(newState, path, processedValue);
            changes.push({ path, value: processedValue, oldValue });
        });

        this.updateState(newState, {
            type: 'BATCH',
            changes
        });

        return changes;
    }

    /**
     * Merge object into state path
     */
    merge(path, value, meta = {}) {
        const current = this.get(path);

        if (typeof current === 'object' && typeof value === 'object') {
            const merged = { ...current, ...value };
            return this.set(path, merged, { ...meta, type: 'MERGE' });
        }

        return this.set(path, value, meta);
    }

    /**
     * Push item to array state
     */
    push(path, item, meta = {}) {
        const current = this.get(path);

        if (Array.isArray(current)) {
            const newArray = [...current, item];
            return this.set(path, newArray, { ...meta, type: 'PUSH' });
        }

        throw new Error(`Cannot push to non-array at path: ${path}`);
    }

    /**
     * Remove item from array state
     */
    remove(path, predicate, meta = {}) {
        const current = this.get(path);

        if (Array.isArray(current)) {
            const newArray = current.filter(
                typeof predicate === 'function'
                    ? item => !predicate(item)
                    : item => item !== predicate
            );
            return this.set(path, newArray, { ...meta, type: 'REMOVE' });
        }

        throw new Error(`Cannot remove from non-array at path: ${path}`);
    }

    /**
     * Delete state property
     */
    delete(path, meta = {}) {
        const newState = this.deepClone(this.state);
        this.deleteNestedValue(newState, path);

        this.updateState(newState, {
            type: 'DELETE',
            path,
            ...meta
        });
    }

    /**
     * Reset state to initial or provided state
     */
    reset(newState = null, meta = {}) {
        const resetState = newState || this.deepClone(this.initialState);

        this.updateState(resetState, {
            type: 'RESET',
            ...meta
        });
    }

    /**
     * Update entire state
     */
    updateState(newState, action = {}) {
        const oldState = this.state;
        this.state = newState;

        // Add to history
        this.addToHistory(newState, action);

        // Clear computed cache
        this.computedCache.clear();

        // Notify subscribers
        this.notifySubscribers(oldState, newState, action);

        // Persist state
        if (this.options.persistence) {
            this.debouncedPersist();
        }

        // Emit global event
        this.eventBus?.emit('state:changed', {
            oldState,
            newState,
            action
        });

        this.debug('State updated', action, newState);
    }

    /**
     * Notify all relevant subscribers
     */
    notifySubscribers(oldState, newState, action) {
        // Notify global subscribers
        this.globalSubscribers.forEach(callback => {
            try {
                callback(newState, oldState, action);
            } catch (error) {
                console.error('Error in global state subscriber:', error);
            }
        });

        // Notify path-specific subscribers
        this.subscribers.forEach((subscribers, path) => {
            const oldValue = this.getNestedValue(oldState, path);
            const newValue = this.getNestedValue(newState, path);

            if (this.hasValueChanged(oldValue, newValue)) {
                subscribers.forEach(subscriber => {
                    try {
                        subscriber.callback(newValue, oldValue, path, action);
                    } catch (error) {
                        console.error(`Error in state subscriber for path "${path}":`, error);
                    }
                });
            }
        });
    }

    /**
     * Check if value has changed
     */
    hasValueChanged(oldValue, newValue) {
        if (oldValue === newValue) return false;

        // Deep comparison for objects
        if (typeof oldValue === 'object' && typeof newValue === 'object') {
            return JSON.stringify(oldValue) !== JSON.stringify(newValue);
        }

        return true;
    }

    /**
     * Add computed property
     */
    addComputed(name, computeFn, dependencies = []) {
        this.computed.set(name, {
            compute: computeFn,
            dependencies
        });

        // Clear cache when dependencies change
        dependencies.forEach(dep => {
            this.subscribe(dep, () => {
                this.computedCache.delete(name);
            });
        });
    }

    /**
     * Get computed property value
     */
    getComputed(name) {
        if (this.computedCache.has(name)) {
            return this.computedCache.get(name);
        }

        const computed = this.computed.get(name);
        if (!computed) {
            throw new Error(`Computed property "${name}" not found`);
        }

        const value = computed.compute(this.state, this);
        this.computedCache.set(name, value);

        return value;
    }

    /**
     * Add middleware
     */
    use(middleware) {
        this.middleware.push(middleware);
    }

    /**
     * Apply middleware to value
     */
    applyMiddleware(type, path, value, oldValue) {
        return this.middleware.reduce((val, middleware) => {
            return middleware(type, path, val, oldValue, this) || val;
        }, value);
    }

    /**
     * Undo last action
     */
    undo() {
        if (this.historyIndex > 0) {
            this.historyIndex--;
            const historyEntry = this.history[this.historyIndex];

            this.state = this.deepClone(historyEntry.state);
            this.notifySubscribers({}, this.state, {
                type: 'UNDO',
                undoneAction: historyEntry.action
            });

            this.eventBus?.emit('state:undo', historyEntry);
            return true;
        }
        return false;
    }

    /**
     * Redo last undone action
     */
    redo() {
        if (this.historyIndex < this.history.length - 1) {
            this.historyIndex++;
            const historyEntry = this.history[this.historyIndex];

            this.state = this.deepClone(historyEntry.state);
            this.notifySubscribers({}, this.state, {
                type: 'REDO',
                redoneAction: historyEntry.action
            });

            this.eventBus?.emit('state:redo', historyEntry);
            return true;
        }
        return false;
    }

    /**
     * Add state to history
     */
    addToHistory(state, action) {
        // Remove future history if we're not at the end
        if (this.historyIndex < this.history.length - 1) {
            this.history = this.history.slice(0, this.historyIndex + 1);
        }

        // Add new entry
        this.history.push({
            state: this.deepClone(state),
            action,
            timestamp: Date.now()
        });

        // Limit history size
        if (this.history.length > this.options.maxHistorySize) {
            this.history.shift();
        } else {
            this.historyIndex++;
        }
    }

    /**
     * Persist state to localStorage
     */
    persistState() {
        if (!this.options.persistence) return;

        try {
            const stateToSave = {
                state: this.state,
                timestamp: Date.now(),
                version: '2.2'
            };

            localStorage.setItem(this.options.storageKey, JSON.stringify(stateToSave));
            this.debug('State persisted to localStorage');
        } catch (error) {
            console.error('Failed to persist state:', error);
        }
    }

    /**
     * Load persisted state from localStorage
     */
    loadPersistedState() {
        try {
            const saved = localStorage.getItem(this.options.storageKey);
            if (saved) {
                const parsed = JSON.parse(saved);

                // Merge with default state to handle new properties
                this.state = this.deepMerge(this.getDefaultState(), parsed.state || {});

                this.debug('State loaded from localStorage');
            }
        } catch (error) {
            console.error('Failed to load persisted state:', error);
            this.state = this.getDefaultState();
        }
    }

    // UI Binding Methods

    /**
     * Bind DOM element to state path
     */
    bindElement(element, statePath, options = {}) {
        const binding = {
            element,
            statePath,
            type: options.type || 'text',
            transform: options.transform || (value => value),
            events: options.events || ['input', 'change'],
            id: this.generateId()
        };

        this.domBindings.set(binding.id, binding);

        // Set initial value
        this.updateDOMElement(binding);

        // Subscribe to state changes
        const unsubscribe = this.subscribe(statePath, (newValue) => {
            this.updateDOMElement(binding, newValue);
        });

        // Listen for DOM events
        const handleDOMChange = (event) => {
            let value = event.target.value;

            if (binding.type === 'checkbox') {
                value = event.target.checked;
            } else if (binding.type === 'number') {
                value = parseFloat(value) || 0;
            }

            this.set(statePath, value, { source: 'dom', element: element.id });
        };

        binding.events.forEach(eventType => {
            element.addEventListener(eventType, handleDOMChange);
        });

        // Return cleanup function
        return () => {
            unsubscribe();
            this.domBindings.delete(binding.id);
            binding.events.forEach(eventType => {
                element.removeEventListener(eventType, handleDOMChange);
            });
        };
    }

    /**
     * Bind form to state object
     */
    bindForm(form, statePath, options = {}) {
        const binding = {
            form,
            statePath,
            fields: new Map(),
            id: this.generateId(),
            autoSubmit: options.autoSubmit || false,
            submitEndpoint: options.submitEndpoint
        };

        // Bind each form field
        const formElements = form.querySelectorAll('input, select, textarea');
        formElements.forEach(element => {
            const fieldPath = `${statePath}.${element.name || element.id}`;
            if (fieldPath && element.name) {
                const fieldBinding = this.bindElement(element, fieldPath, {
                    type: element.type,
                    events: ['input', 'change', 'blur']
                });
                binding.fields.set(element.name, fieldBinding);
            }
        });

        this.formBindings.set(binding.id, binding);

        // Handle form submission
        const handleSubmit = (event) => {
            event.preventDefault();
            this.submitForm(binding);
        };

        form.addEventListener('submit', handleSubmit);

        return () => {
            binding.fields.forEach(cleanup => cleanup());
            this.formBindings.delete(binding.id);
            form.removeEventListener('submit', handleSubmit);
        };
    }

    /**
     * Update DOM element with state value
     */
    updateDOMElement(binding, value = null) {
        const currentValue = value !== null ? value : this.get(binding.statePath);
        const transformedValue = binding.transform(currentValue);

        switch (binding.type) {
            case 'text':
            case 'email':
            case 'password':
            case 'number':
                if (binding.element.value !== transformedValue) {
                    binding.element.value = transformedValue || '';
                }
                break;
            case 'checkbox':
                binding.element.checked = Boolean(transformedValue);
                break;
            case 'radio':
                binding.element.checked = binding.element.value === transformedValue;
                break;
            case 'select':
                binding.element.value = transformedValue || '';
                break;
            case 'innerHTML':
                binding.element.innerHTML = transformedValue || '';
                break;
            case 'textContent':
                binding.element.textContent = transformedValue || '';
                break;
            case 'class':
                if (transformedValue) {
                    binding.element.classList.add(transformedValue);
                } else {
                    binding.element.classList.remove(binding.element.dataset.boundClass);
                }
                binding.element.dataset.boundClass = transformedValue;
                break;
        }
    }

    /**
     * Submit form data to API
     */
    async submitForm(binding) {
        if (!this.apiService || !binding.submitEndpoint) return;

        const formData = this.get(binding.statePath);

        try {
            this.set('ui.loading', true);
            this.set('ui.error', null);

            const response = await this.apiService.request(
                binding.submitEndpoint.method || 'POST',
                binding.submitEndpoint.url,
                formData
            );

            if (response.success) {
                this.set('ui.notifications', [
                    ...this.get('ui.notifications'),
                    {
                        id: this.generateId(),
                        type: 'success',
                        message: 'Daten erfolgreich gespeichert',
                        timestamp: Date.now()
                    }
                ]);

                // Clear form if specified
                if (binding.submitEndpoint.clearAfterSubmit) {
                    this.reset(binding.statePath);
                }
            }

        } catch (error) {
            this.set('ui.error', error.message);
            this.set('ui.notifications', [
                ...this.get('ui.notifications'),
                {
                    id: this.generateId(),
                    type: 'error',
                    message: `Fehler beim Speichern: ${error.message}`,
                    timestamp: Date.now()
                }
            ]);
        } finally {
            this.set('ui.loading', false);
        }
    }

    /**
     * Set up mutation observer for automatic UI binding
     */
    setupUIObserver() {
        if (typeof MutationObserver === 'undefined') return;

        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                mutation.addedNodes.forEach((node) => {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        this.autoBindElements(node);
                    }
                });
            });
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        // Initial binding
        this.autoBindElements(document.body);
    }

    /**
     * Automatically bind elements with data attributes
     */
    autoBindElements(root) {
        // Bind elements with data-bind attribute
        const bindElements = root.querySelectorAll('[data-bind]');
        bindElements.forEach(element => {
            const statePath = element.dataset.bind;
            const bindType = element.dataset.bindType || 'text';

            if (statePath && !element.dataset.boundByState) {
                element.dataset.boundByState = 'true';
                this.bindElement(element, statePath, { type: bindType });
            }
        });

        // Bind forms with data-bind-form attribute
        const bindForms = root.querySelectorAll('form[data-bind-form]');
        bindForms.forEach(form => {
            const statePath = form.dataset.bindForm;

            if (statePath && !form.dataset.boundByState) {
                form.dataset.boundByState = 'true';
                this.bindForm(form, statePath, {
                    autoSubmit: form.dataset.autoSubmit === 'true',
                    submitEndpoint: form.dataset.submitEndpoint ? JSON.parse(form.dataset.submitEndpoint) : null
                });
            }
        });
    }

    // API Synchronization Methods

    /**
     * Start automatic synchronization with server
     */
    startAutoSync() {
        if (this.syncInterval) return;

        const interval = this.get('user.settings.syncInterval') || 300000; // 5 minutes default

        this.syncInterval = setInterval(() => {
            this.syncWithServer();
        }, interval);

        // Initial sync
        this.syncWithServer();
    }

    /**
     * Stop automatic synchronization
     */
    stopAutoSync() {
        if (this.syncInterval) {
            clearInterval(this.syncInterval);
            this.syncInterval = null;
        }
    }

    /**
     * Synchronize state with server
     */
    async syncWithServer() {
        if (!this.apiService) return;

        try {
            this.set('system.syncStatus', 'syncing');

            // Sync events
            await this.syncEvents();

            // Sync templates
            await this.syncTemplates();

            // Sync calendars
            await this.syncCalendars();

            // Sync user settings
            await this.syncUserSettings();

            this.set('system.lastSync', Date.now());
            this.set('system.syncStatus', 'idle');
            this.lastServerSync = Date.now();

            this.debug('Server sync completed');

        } catch (error) {
            this.set('system.syncStatus', 'error');
            console.error('Server sync failed:', error);

            // Retry after delay
            setTimeout(() => {
                if (this.get('user.settings.autoSync')) {
                    this.syncWithServer();
                }
            }, 30000); // Retry after 30 seconds
        }
    }

    /**
     * Sync events with server
     */
    async syncEvents() {
        try {
            const response = await this.apiService.request('GET', '/api/v2/events', {
                limit: 1000,
                start: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0], // Last 7 days
                end: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0] // Next 30 days
            });

            if (response.success && response.events) {
                this.set('data.events', response.events);
            }
        } catch (error) {
            console.error('Failed to sync events:', error);
        }
    }

    /**
     * Sync templates with server
     */
    async syncTemplates() {
        try {
            const response = await this.apiService.request('GET', '/api/v1/templates');

            if (response.success && response.templates) {
                this.set('data.templates', response.templates);
            }
        } catch (error) {
            console.error('Failed to sync templates:', error);
        }
    }

    /**
     * Sync calendars with server
     */
    async syncCalendars() {
        try {
            const response = await this.apiService.request('GET', '/api/v2/calendars');

            if (response.success && response.calendars) {
                const calendarIds = response.calendars.map(cal => cal.id);
                this.set('data.calendars', calendarIds);
            }
        } catch (error) {
            console.error('Failed to sync calendars:', error);
        }
    }

    /**
     * Sync user settings to server
     */
    async syncUserSettings() {
        // This would typically send user preferences to server
        // For now, just update local sync timestamp
        const settings = this.get('user.settings');

        try {
            // Example API call to save settings
            // await this.apiService.request('PUT', '/api/v1/user/settings', settings);
        } catch (error) {
            console.error('Failed to sync user settings:', error);
        }
    }

    /**
     * Make API request with state integration
     */
    async apiRequest(method, endpoint, data = null, options = {}) {
        if (!this.apiService) {
            throw new Error('API service not available');
        }

        const requestId = this.generateId();

        try {
            // Track pending request
            this.pendingRequests.set(requestId, { method, endpoint, timestamp: Date.now() });
            this.set('system.activeRequests', this.pendingRequests.size);

            const response = await this.apiService.request(method, endpoint, data);

            // Handle response
            if (response.success) {
                // Auto-update state based on response
                this.handleAPIResponse(method, endpoint, response, options);
            }

            return response;

        } catch (error) {
            this.set('ui.error', error.message);
            throw error;
        } finally {
            // Remove from pending requests
            this.pendingRequests.delete(requestId);
            this.set('system.activeRequests', this.pendingRequests.size);
        }
    }

    /**
     * Handle API response and update state
     */
    handleAPIResponse(method, endpoint, response, options) {
        // Auto-update patterns based on endpoint
        if (endpoint.includes('/events')) {
            if (method === 'GET' && response.events) {
                this.set('data.events', response.events);
            } else if (method === 'POST' && response.event) {
                this.push('data.events', response.event);
            }
        } else if (endpoint.includes('/templates')) {
            if (method === 'GET' && response.templates) {
                this.set('data.templates', response.templates);
            } else if (method === 'POST' && response.template) {
                this.push('data.templates', response.template);
            }
        }

        // Custom update logic
        if (options.updatePath) {
            this.set(options.updatePath, response.data || response);
        }

        // Trigger sync if specified
        if (options.triggerSync) {
            this.debouncedSync();
        }
    }

    // Utility methods

    /**
     * Set nested value by path
     */
    setNestedValue(obj, path, value) {
        const keys = path.split('.');
        const lastKey = keys.pop();
        const target = keys.reduce((o, key) => {
            if (!(key in o)) o[key] = {};
            return o[key];
        }, obj);
        target[lastKey] = value;
    }

    /**
     * Get nested value by path
     */
    getNestedValue(obj, path) {
        return path.split('.').reduce((o, key) => {
            return o && o[key] !== undefined ? o[key] : undefined;
        }, obj);
    }

    /**
     * Delete nested value by path
     */
    deleteNestedValue(obj, path) {
        const keys = path.split('.');
        const lastKey = keys.pop();
        const target = keys.reduce((o, key) => o && o[key], obj);
        if (target) {
            delete target[lastKey];
        }
    }

    /**
     * Deep clone object
     */
    deepClone(obj) {
        if (obj === null || typeof obj !== 'object') return obj;
        if (obj instanceof Date) return new Date(obj);
        if (obj instanceof Array) return obj.map(item => this.deepClone(item));
        if (typeof obj === 'object') {
            const cloned = {};
            Object.keys(obj).forEach(key => {
                cloned[key] = this.deepClone(obj[key]);
            });
            return cloned;
        }
    }

    /**
     * Deep merge objects
     */
    deepMerge(target, source) {
        const result = this.deepClone(target);

        for (const key in source) {
            if (source.hasOwnProperty(key)) {
                if (typeof source[key] === 'object' && source[key] !== null && !Array.isArray(source[key])) {
                    result[key] = this.deepMerge(result[key] || {}, source[key]);
                } else {
                    result[key] = source[key];
                }
            }
        }

        return result;
    }

    /**
     * Debounce function
     */
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    /**
     * Generate unique ID
     */
    generateId() {
        return `state_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * Debug logging
     */
    debug(...args) {
        if (this.options.debug) {
            console.log('[StateManager]', ...args);
        }
    }

    /**
     * Get debug info
     */
    getDebugInfo() {
        return {
            stateSize: JSON.stringify(this.state).length,
            subscribers: Array.from(this.subscribers.keys()),
            globalSubscribers: this.globalSubscribers.size,
            historySize: this.history.length,
            historyIndex: this.historyIndex,
            computedProperties: Array.from(this.computed.keys()),
            cachedComputed: Array.from(this.computedCache.keys()),
            middleware: this.middleware.length
        };
    }
}

// Create global state manager instance
window.ChronosState = window.ChronosState || new ChronosStateManager({
    persistence: true,
    storageKey: 'chronos_app_state',
    debug: localStorage.getItem('chronos_debug') === 'true'
});

// Export for global use
window.ChronosStateManager = ChronosStateManager;

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ChronosStateManager;
}