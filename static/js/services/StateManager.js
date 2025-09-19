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

        // Debounced persistence
        this.debouncedPersist = this.debounce(
            this.persistState.bind(this),
            this.options.debounceDelay
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