/**
 * Base Component Class for Chronos UI Components
 * Provides common functionality and lifecycle methods
 */
class ChronosComponent {
    constructor(element, options = {}) {
        this.element = element;
        this.options = { ...this.defaultOptions, ...options };
        this.state = { ...this.defaultState };
        this.eventBus = window.ChronosEventBus;
        this.listeners = new Map();
        this.childComponents = new Set();
        this.parentComponent = null;
        this.isInitialized = false;
        this.isDestroyed = false;

        // Bind methods to preserve context
        this.boundHandlers = new Map();

        this.init();
    }

    /**
     * Default options - override in subclasses
     */
    get defaultOptions() {
        return {
            debug: false,
            autoUpdate: true,
            className: 'chronos-component'
        };
    }

    /**
     * Default state - override in subclasses
     */
    get defaultState() {
        return {
            loading: false,
            error: null,
            data: null
        };
    }

    /**
     * Component initialization
     */
    init() {
        if (this.isDestroyed) {
            throw new Error('Cannot initialize destroyed component');
        }

        this.debug('Initializing component');

        // Add component class
        if (this.element && this.options.className) {
            this.element.classList.add(this.options.className);
        }

        // Set up DOM references
        this.setupDOMReferences();

        // Set up event listeners
        this.setupEventListeners();

        // Initial render
        this.render();

        // Mark as initialized
        this.isInitialized = true;

        // Emit initialization event
        this.emit('component:initialized', this);

        this.debug('Component initialized');
    }

    /**
     * Set up DOM element references
     * Override in subclasses to define specific selectors
     */
    setupDOMReferences() {
        this.refs = {};

        // Find all elements with data-ref attribute
        if (this.element) {
            this.element.querySelectorAll('[data-ref]').forEach(el => {
                const ref = el.getAttribute('data-ref');
                this.refs[ref] = el;
            });
        }
    }

    /**
     * Set up event listeners
     * Override in subclasses to add specific listeners
     */
    setupEventListeners() {
        // Add default component event listeners
        if (this.element) {
            this.addEventListener(this.element, 'click', this.handleClick.bind(this));
        }
    }

    /**
     * Add event listener with automatic cleanup
     */
    addEventListener(element, event, handler, options = {}) {
        if (!element || typeof handler !== 'function') return;

        const boundHandler = handler.bind(this);
        element.addEventListener(event, boundHandler, options);

        // Store for cleanup
        const key = `${element}_${event}_${Date.now()}`;
        this.listeners.set(key, {
            element,
            event,
            handler: boundHandler,
            options
        });

        return () => this.removeEventListener(key);
    }

    /**
     * Remove specific event listener
     */
    removeEventListener(key) {
        if (this.listeners.has(key)) {
            const { element, event, handler } = this.listeners.get(key);
            element.removeEventListener(event, handler);
            this.listeners.delete(key);
        }
    }

    /**
     * Subscribe to event bus events
     */
    subscribe(eventName, handler) {
        const unsubscribe = this.eventBus.on(eventName, handler, this);

        // Store for cleanup
        const key = `eventbus_${eventName}_${Date.now()}`;
        this.listeners.set(key, { unsubscribe });

        return unsubscribe;
    }

    /**
     * Emit event on event bus
     */
    emit(eventName, ...args) {
        this.eventBus.emit(eventName, ...args);
    }

    /**
     * Default click handler
     */
    handleClick(event) {
        // Can be overridden in subclasses
        this.debug('Click event:', event);
    }

    /**
     * Update component state
     */
    setState(newState, shouldRender = true) {
        if (this.isDestroyed) return;

        const oldState = { ...this.state };
        this.state = { ...this.state, ...newState };

        this.emit('component:stateChange', this, oldState, this.state);

        if (shouldRender && this.options.autoUpdate) {
            this.render();
        }

        this.debug('State updated:', { oldState, newState: this.state });
    }

    /**
     * Get current state
     */
    getState() {
        return { ...this.state };
    }

    /**
     * Update component options
     */
    setOptions(newOptions) {
        if (this.isDestroyed) return;

        this.options = { ...this.options, ...newOptions };
        this.emit('component:optionsChange', this, newOptions);

        if (this.options.autoUpdate) {
            this.render();
        }
    }

    /**
     * Render component - override in subclasses
     */
    render() {
        if (this.isDestroyed || !this.element) return;

        this.debug('Rendering component');
        this.emit('component:beforeRender', this);

        // Default render implementation
        this.updateElement();

        this.emit('component:afterRender', this);
    }

    /**
     * Update element content - override in subclasses
     */
    updateElement() {
        // Default implementation - subclasses should override
        if (this.element && this.state.data) {
            // Simple text update as fallback
            if (typeof this.state.data === 'string') {
                this.element.textContent = this.state.data;
            }
        }
    }

    /**
     * Show loading state
     */
    showLoading(message = 'Loading...') {
        this.setState({ loading: true, error: null });
        this.element?.classList.add('loading');
        this.element?.setAttribute('aria-busy', 'true');

        if (message && this.refs.loadingText) {
            this.refs.loadingText.textContent = message;
        }
    }

    /**
     * Hide loading state
     */
    hideLoading() {
        this.setState({ loading: false });
        this.element?.classList.remove('loading');
        this.element?.removeAttribute('aria-busy');
    }

    /**
     * Show error state
     */
    showError(error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        this.setState({ error: errorMessage, loading: false });
        this.element?.classList.add('error');

        if (this.refs.errorText) {
            this.refs.errorText.textContent = errorMessage;
        }

        this.emit('component:error', this, error);
    }

    /**
     * Clear error state
     */
    clearError() {
        this.setState({ error: null });
        this.element?.classList.remove('error');

        if (this.refs.errorText) {
            this.refs.errorText.textContent = '';
        }
    }

    /**
     * Add child component
     */
    addChild(component) {
        if (component instanceof ChronosComponent) {
            this.childComponents.add(component);
            component.parentComponent = this;
            this.debug('Child component added:', component);
        }
    }

    /**
     * Remove child component
     */
    removeChild(component) {
        if (this.childComponents.has(component)) {
            this.childComponents.delete(component);
            component.parentComponent = null;
            this.debug('Child component removed:', component);
        }
    }

    /**
     * Find child component by type or element
     */
    findChild(predicate) {
        for (const child of this.childComponents) {
            if (typeof predicate === 'function' && predicate(child)) {
                return child;
            }
            if (typeof predicate === 'string' && child.constructor.name === predicate) {
                return child;
            }
        }
        return null;
    }

    /**
     * Destroy component and cleanup
     */
    destroy() {
        if (this.isDestroyed) return;

        this.debug('Destroying component');

        // Emit before destroy event
        this.emit('component:beforeDestroy', this);

        // Destroy child components
        for (const child of this.childComponents) {
            child.destroy();
        }
        this.childComponents.clear();

        // Remove from parent
        if (this.parentComponent) {
            this.parentComponent.removeChild(this);
        }

        // Cleanup event listeners
        for (const [key, listener] of this.listeners) {
            if (listener.unsubscribe) {
                listener.unsubscribe();
            } else if (listener.element && listener.handler) {
                listener.element.removeEventListener(listener.event, listener.handler);
            }
        }
        this.listeners.clear();

        // Remove element classes
        if (this.element) {
            this.element.classList.remove(this.options.className);
            this.element.removeAttribute('aria-busy');
        }

        // Mark as destroyed
        this.isDestroyed = true;
        this.isInitialized = false;

        // Emit destroy event
        this.emit('component:destroyed', this);

        this.debug('Component destroyed');
    }

    /**
     * Debug logging
     */
    debug(...args) {
        if (this.options.debug) {
            console.log(`[${this.constructor.name}]`, ...args);
        }
    }

    /**
     * Get component info
     */
    getInfo() {
        return {
            type: this.constructor.name,
            initialized: this.isInitialized,
            destroyed: this.isDestroyed,
            element: this.element?.tagName,
            children: this.childComponents.size,
            listeners: this.listeners.size,
            state: this.state,
            options: this.options
        };
    }
}

// Export for global use
window.ChronosComponent = ChronosComponent;

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ChronosComponent;
}