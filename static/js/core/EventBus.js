/**
 * Chronos Event Bus - Central communication system
 * Implements publish-subscribe pattern for component communication
 */
class ChronosEventBus {
    constructor() {
        this.events = new Map();
        this.globalListeners = new Map();
    }

    /**
     * Subscribe to an event
     * @param {string} eventName - Event name
     * @param {Function} callback - Event handler
     * @param {Object} context - Optional context for callback
     * @returns {Function} Unsubscribe function
     */
    on(eventName, callback, context = null) {
        if (!this.events.has(eventName)) {
            this.events.set(eventName, new Set());
        }

        const listener = { callback, context, id: this.generateId() };
        this.events.get(eventName).add(listener);

        // Return unsubscribe function
        return () => this.off(eventName, listener.id);
    }

    /**
     * Subscribe to an event once
     * @param {string} eventName - Event name
     * @param {Function} callback - Event handler
     * @param {Object} context - Optional context
     * @returns {Function} Unsubscribe function
     */
    once(eventName, callback, context = null) {
        const unsubscribe = this.on(eventName, (...args) => {
            unsubscribe();
            callback.apply(context, args);
        }, context);
        return unsubscribe;
    }

    /**
     * Unsubscribe from an event
     * @param {string} eventName - Event name
     * @param {string} listenerId - Listener ID
     */
    off(eventName, listenerId) {
        if (!this.events.has(eventName)) return;

        const listeners = this.events.get(eventName);
        for (const listener of listeners) {
            if (listener.id === listenerId) {
                listeners.delete(listener);
                break;
            }
        }

        if (listeners.size === 0) {
            this.events.delete(eventName);
        }
    }

    /**
     * Emit an event
     * @param {string} eventName - Event name
     * @param {...any} args - Event arguments
     */
    emit(eventName, ...args) {
        if (!this.events.has(eventName)) return;

        const listeners = Array.from(this.events.get(eventName));

        listeners.forEach(listener => {
            try {
                listener.callback.apply(listener.context, args);
            } catch (error) {
                console.error(`Error in event listener for "${eventName}":`, error);
                this.emit('error', error, eventName, listener);
            }
        });

        // Emit to global listeners
        this.emitGlobal(eventName, ...args);
    }

    /**
     * Add global event listener (listens to all events)
     * @param {Function} callback - Global listener
     * @returns {Function} Unsubscribe function
     */
    onGlobal(callback) {
        const id = this.generateId();
        this.globalListeners.set(id, callback);

        return () => this.globalListeners.delete(id);
    }

    /**
     * Emit to global listeners
     * @param {string} eventName - Event name
     * @param {...any} args - Event arguments
     */
    emitGlobal(eventName, ...args) {
        this.globalListeners.forEach(callback => {
            try {
                callback(eventName, ...args);
            } catch (error) {
                console.error('Error in global event listener:', error);
            }
        });
    }

    /**
     * Generate unique ID
     * @returns {string} Unique ID
     */
    generateId() {
        return `listener_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * Get all active event names
     * @returns {Array<string>} Event names
     */
    getEventNames() {
        return Array.from(this.events.keys());
    }

    /**
     * Get listener count for event
     * @param {string} eventName - Event name
     * @returns {number} Listener count
     */
    getListenerCount(eventName) {
        return this.events.has(eventName) ? this.events.get(eventName).size : 0;
    }

    /**
     * Clear all listeners
     */
    clear() {
        this.events.clear();
        this.globalListeners.clear();
    }

    /**
     * Debug information
     * @returns {Object} Debug info
     */
    debug() {
        const events = {};
        for (const [eventName, listeners] of this.events) {
            events[eventName] = listeners.size;
        }

        return {
            events,
            globalListeners: this.globalListeners.size,
            totalEvents: this.events.size,
            totalListeners: Array.from(this.events.values()).reduce((sum, listeners) => sum + listeners.size, 0)
        };
    }
}

// Create global event bus instance
window.ChronosEventBus = window.ChronosEventBus || new ChronosEventBus();

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ChronosEventBus;
}