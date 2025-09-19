/**
 * Chronos Engine - Main Application Controller
 * Coordinates all components and manages global application state
 */

class ChronosApplication {
    constructor() {
        this.eventBus = window.ChronosEventBus;
        this.state = window.ChronosState;
        this.api = window.ChronosAPI;

        this.components = new Map();
        this.activeModals = new Set();

        this.isInitialized = false;
        this.config = window.ChronosConfig || {};

        // Bind methods
        this.handleKeyboardShortcuts = this.handleKeyboardShortcuts.bind(this);
        this.handleVisibilityChange = this.handleVisibilityChange.bind(this);
        this.handleOnline = this.handleOnline.bind(this);
        this.handleOffline = this.handleOffline.bind(this);
    }

    /**
     * Initialize the application
     */
    async initialize() {
        if (this.isInitialized) return;

        console.log('🚀 Chronos Engine v2.2 initializing...');

        try {
            // Set up global event listeners
            this.setupGlobalEventListeners();

            // Initialize API service with config
            this.initializeAPIService();

            // Set up state management
            this.initializeStateManagement();

            // Initialize UI theme
            this.initializeTheme();

            // Initialize global components
            await this.initializeGlobalComponents();

            // Set up error handling
            this.setupErrorHandling();

            // Check initial connectivity
            await this.checkConnectivity();

            // Set up auto-sync if enabled
            this.setupAutoSync();

            this.isInitialized = true;

            // Emit initialization event
            this.eventBus.emit('app:initialized');

            console.log('✅ Chronos Engine initialized successfully');

        } catch (error) {
            console.error('❌ Failed to initialize Chronos Engine:', error);
            this.showCriticalError('Failed to initialize application', error);
        }
    }

    /**
     * Set up global event listeners
     */
    setupGlobalEventListeners() {
        // Keyboard shortcuts
        document.addEventListener('keydown', this.handleKeyboardShortcuts);

        // Page visibility
        document.addEventListener('visibilitychange', this.handleVisibilityChange);

        // Network status
        window.addEventListener('online', this.handleOnline);
        window.addEventListener('offline', this.handleOffline);

        // Window unload
        window.addEventListener('beforeunload', (e) => {
            if (this.hasUnsavedChanges()) {
                e.preventDefault();
                e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
            }
        });

        // Global error handling
        window.addEventListener('error', (e) => {
            console.error('Global JavaScript error:', e.error);
            this.eventBus.emit('app:error', e.error);
        });

        window.addEventListener('unhandledrejection', (e) => {
            console.error('Unhandled promise rejection:', e.reason);
            this.eventBus.emit('app:error', e.reason);
        });
    }

    /**
     * Initialize API service
     */
    initializeAPIService() {
        // Configure API service with app config
        if (this.config.api) {
            this.api.baseURL = this.config.api.baseURL;
            this.api.timeout = this.config.api.timeout;
            this.api.retryAttempts = this.config.api.retryAttempts;
        }

        // Set up API event listeners
        this.eventBus.on('api:requestStart', (data) => {
            this.state.set('system.activeRequests', this.state.get('system.activeRequests') + 1);
        });

        this.eventBus.on('api:requestSuccess', (data) => {
            this.state.set('system.activeRequests', Math.max(0, this.state.get('system.activeRequests') - 1));
            this.state.set('system.apiConnected', true);
        });

        this.eventBus.on('api:requestError', (data) => {
            this.state.set('system.activeRequests', Math.max(0, this.state.get('system.activeRequests') - 1));

            if (data.error?.isNetworkError) {
                this.state.set('system.apiConnected', false);
            }
        });
    }

    /**
     * Initialize state management
     */
    initializeStateManagement() {
        // Set initial app configuration in state
        this.state.merge('ui', {
            theme: this.config.ui?.theme || 'dark',
            language: this.config.ui?.language || 'de',
            timezone: this.config.ui?.timezone || 'Europe/Berlin'
        });

        this.state.merge('features', this.config.features || {});

        // Subscribe to critical state changes
        this.state.subscribe('system.online', (online) => {
            this.updateConnectionStatus(online);
        });

        this.state.subscribe('system.apiConnected', (connected) => {
            this.updateConnectionStatus(connected && this.state.get('system.online'));
        });

        this.state.subscribe('ui.theme', (theme) => {
            this.applyTheme(theme);
        });
    }

    /**
     * Initialize theme
     */
    initializeTheme() {
        const savedTheme = localStorage.getItem('chronos_theme');
        const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        const theme = savedTheme || this.config.ui?.theme || systemTheme;

        this.applyTheme(theme);
        this.state.set('ui.theme', theme);

        // Listen for system theme changes
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            if (!localStorage.getItem('chronos_theme')) {
                const newTheme = e.matches ? 'dark' : 'light';
                this.applyTheme(newTheme);
                this.state.set('ui.theme', newTheme);
            }
        });
    }

    /**
     * Apply theme to document
     */
    applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('chronos_theme', theme);
    }

    /**
     * Initialize global components
     */
    async initializeGlobalComponents() {
        // Initialize toast system
        this.initializeToastSystem();

        // Initialize modal system
        this.initializeModalSystem();

        // Initialize header components
        this.initializeHeaderComponents();

        // Initialize help system
        this.initializeHelpSystem();
    }

    /**
     * Initialize toast notification system
     */
    initializeToastSystem() {
        // Create toast container if it doesn't exist
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container';
            container.setAttribute('aria-live', 'polite');
            container.setAttribute('aria-label', 'Notifications');
            document.body.appendChild(container);
        }

        // Subscribe to notification events
        this.eventBus.on('notify:success', (data) => {
            this.showToast('success', data.title, data.message);
        });

        this.eventBus.on('notify:error', (data) => {
            this.showToast('error', data.title, data.message);
        });

        this.eventBus.on('notify:warning', (data) => {
            this.showToast('warning', data.title, data.message);
        });

        this.eventBus.on('notify:info', (data) => {
            this.showToast('info', data.title, data.message);
        });
    }

    /**
     * Initialize modal system
     */
    initializeModalSystem() {
        // Handle modal backdrop clicks
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal-backdrop')) {
                const modal = e.target.closest('.modal');
                if (modal) {
                    this.closeModal(modal);
                }
            }
        });

        // Handle modal close buttons
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal-close')) {
                const modal = e.target.closest('.modal');
                if (modal) {
                    this.closeModal(modal);
                }
            }
        });
    }

    /**
     * Initialize header components
     */
    initializeHeaderComponents() {
        // Settings button
        const settingsBtn = document.getElementById('settings-btn');
        if (settingsBtn) {
            settingsBtn.addEventListener('click', () => {
                this.openSettings();
            });
        }

        // Help button
        const helpBtn = document.getElementById('help-btn');
        if (helpBtn) {
            helpBtn.addEventListener('click', () => {
                this.showHelp();
            });
        }

        // Update navigation active state
        this.updateNavigationState();
    }

    /**
     * Initialize help system
     */
    initializeHelpSystem() {
        // Global help shortcut
        this.eventBus.on('help:show', () => {
            this.showHelp();
        });
    }

    /**
     * Set up error handling
     */
    setupErrorHandling() {
        this.eventBus.on('app:error', (error) => {
            console.error('Application error:', error);
            this.showToast('error', 'Application Error', 'An unexpected error occurred');
        });

        this.eventBus.on('component:error', (component, error) => {
            console.error(`Component error in ${component.constructor.name}:`, error);
            this.showToast('error', 'Component Error', `Error in ${component.constructor.name}`);
        });
    }

    /**
     * Check connectivity
     */
    async checkConnectivity() {
        const isOnline = navigator.onLine;
        this.state.set('system.online', isOnline);

        if (isOnline) {
            try {
                const isAPIConnected = await this.api.checkHealth();
                this.state.set('system.apiConnected', isAPIConnected);
            } catch {
                this.state.set('system.apiConnected', false);
            }
        }
    }

    /**
     * Set up auto-sync
     */
    setupAutoSync() {
        const autoSync = this.state.get('user.settings.autoSync');
        const syncInterval = this.state.get('user.settings.syncInterval');

        if (autoSync && syncInterval) {
            setInterval(() => {
                if (document.visibilityState === 'visible' && this.state.get('system.apiConnected')) {
                    this.eventBus.emit('sync:auto');
                }
            }, syncInterval);
        }
    }

    /**
     * Handle keyboard shortcuts
     */
    handleKeyboardShortcuts(event) {
        // Skip if typing in input
        if (['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target.tagName)) {
            return;
        }

        // Skip if modal is open and it's not a global shortcut
        if (this.activeModals.size > 0 && !event.ctrlKey && !event.metaKey) {
            return;
        }

        if (event.ctrlKey || event.metaKey) {
            switch (event.key.toLowerCase()) {
                case '/':
                case '?':
                    event.preventDefault();
                    this.showHelp();
                    break;

                case ',':
                    event.preventDefault();
                    this.openSettings();
                    break;

                case 'k':
                    event.preventDefault();
                    this.openCommandPalette();
                    break;
            }
        }

        // Escape key - close modals/overlays
        if (event.key === 'Escape') {
            if (this.activeModals.size > 0) {
                const lastModal = Array.from(this.activeModals).pop();
                this.closeModal(lastModal);
            }
        }
    }

    /**
     * Handle visibility change
     */
    handleVisibilityChange() {
        if (document.visibilityState === 'visible') {
            // Page became visible - check connectivity
            this.checkConnectivity();
            this.eventBus.emit('app:focus');
        } else {
            // Page hidden
            this.eventBus.emit('app:blur');
        }
    }

    /**
     * Handle online event
     */
    handleOnline() {
        this.state.set('system.online', true);
        this.checkConnectivity();
        this.showToast('success', 'Connection Restored', 'You are back online');
    }

    /**
     * Handle offline event
     */
    handleOffline() {
        this.state.set('system.online', false);
        this.state.set('system.apiConnected', false);
        this.showToast('warning', 'Connection Lost', 'You are now offline');
    }

    /**
     * Update connection status display
     */
    updateConnectionStatus(connected) {
        const statusElements = document.querySelectorAll('.connection-status');

        statusElements.forEach(element => {
            const dot = element.querySelector('.status-dot');
            const text = element.querySelector('.status-text');

            if (dot) {
                dot.className = `status-dot ${connected ? 'status-online' : 'status-offline'}`;
            }

            if (text) {
                text.textContent = connected ? 'Online' : 'Offline';
            }
        });
    }

    /**
     * Update navigation active state
     */
    updateNavigationState() {
        const currentPage = this.config.pageData?.currentPage || 'dashboard';
        const navLinks = document.querySelectorAll('.nav-link');

        navLinks.forEach(link => {
            const nav = link.getAttribute('data-nav');
            link.classList.toggle('active', nav === currentPage);
        });
    }

    /**
     * Show toast notification
     */
    showToast(type, title, message, duration = 5000) {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = this.createToastElement(type, title, message);
        container.appendChild(toast);

        // Animate in
        setTimeout(() => toast.classList.add('show'), 10);

        // Auto remove
        setTimeout(() => this.removeToast(toast), duration);

        return toast;
    }

    /**
     * Create toast element
     */
    createToastElement(type, title, message) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;

        const icons = {
            success: '✅',
            warning: '⚠️',
            error: '❌',
            info: 'ℹ️'
        };

        toast.innerHTML = `
            <div class="toast-header">
                <span class="toast-icon">${icons[type] || 'ℹ️'}</span>
                <span class="toast-title">${title}</span>
                <button class="toast-close" aria-label="Close notification">×</button>
            </div>
            <div class="toast-body">${message}</div>
        `;

        // Add close handler
        const closeBtn = toast.querySelector('.toast-close');
        closeBtn.addEventListener('click', () => this.removeToast(toast));

        return toast;
    }

    /**
     * Remove toast notification
     */
    removeToast(toast) {
        if (!toast) return;

        toast.classList.add('fade-out');
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }

    /**
     * Open modal
     */
    openModal(modalId) {
        const modal = document.getElementById(modalId);
        if (!modal) return;

        modal.showModal?.() || this.showModalFallback(modal);
        this.activeModals.add(modal);
        document.body.style.overflow = 'hidden';

        this.eventBus.emit('modal:opened', modalId);
    }

    /**
     * Close modal
     */
    closeModal(modal) {
        if (!modal) return;

        modal.close?.() || this.hideModalFallback(modal);
        this.activeModals.delete(modal);

        if (this.activeModals.size === 0) {
            document.body.style.overflow = '';
        }

        this.eventBus.emit('modal:closed', modal.id);
    }

    /**
     * Show modal fallback for browsers without dialog support
     */
    showModalFallback(modal) {
        modal.style.display = 'flex';
        modal.setAttribute('aria-hidden', 'false');
    }

    /**
     * Hide modal fallback
     */
    hideModalFallback(modal) {
        modal.style.display = 'none';
        modal.setAttribute('aria-hidden', 'true');
    }

    /**
     * Open settings modal
     */
    openSettings() {
        this.openModal('settings-modal');
    }

    /**
     * Show help
     */
    showHelp() {
        const helpContent = `
            <div class="help-content">
                <h3>🚀 Chronos Engine v2.2 Help</h3>

                <div class="help-section">
                    <h4>Keyboard Shortcuts</h4>
                    <div class="shortcuts-grid">
                        <div class="shortcut">
                            <kbd>Ctrl+/</kbd> <span>Show help</span>
                        </div>
                        <div class="shortcut">
                            <kbd>Ctrl+,</kbd> <span>Open settings</span>
                        </div>
                        <div class="shortcut">
                            <kbd>Ctrl+K</kbd> <span>Command palette</span>
                        </div>
                        <div class="shortcut">
                            <kbd>Escape</kbd> <span>Close modals</span>
                        </div>
                    </div>
                </div>

                <div class="help-section">
                    <h4>Features</h4>
                    <ul>
                        <li><strong>Event Management:</strong> Create, edit, and organize events</li>
                        <li><strong>Templates:</strong> Reusable event templates</li>
                        <li><strong>Sub-tasks:</strong> Checkbox-style task lists within events</li>
                        <li><strong>Event Linking:</strong> Connect related events</li>
                        <li><strong>Workflows:</strong> Automated actions and follow-ups</li>
                    </ul>
                </div>

                <div class="help-section">
                    <h4>Support</h4>
                    <p>For additional help, check the <a href="/docs" target="_blank">API documentation</a> or contact support.</p>
                </div>
            </div>
        `;

        this.showModal('Help', helpContent);
    }

    /**
     * Open command palette
     */
    openCommandPalette() {
        // TODO: Implement command palette
        this.showToast('info', 'Command Palette', 'Coming soon!');
    }

    /**
     * Show modal with content
     */
    showModal(title, content) {
        // Create modal element
        const modal = document.createElement('dialog');
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content">
                <header class="modal-header">
                    <h2>${title}</h2>
                    <button class="modal-close" aria-label="Close modal">✕</button>
                </header>
                <div class="modal-body">
                    ${content}
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        modal.showModal?.() || this.showModalFallback(modal);
        this.activeModals.add(modal);

        // Auto-remove after closing
        modal.addEventListener('close', () => {
            this.activeModals.delete(modal);
            document.body.removeChild(modal);
        });

        return modal;
    }

    /**
     * Show critical error
     */
    showCriticalError(title, error) {
        const errorContent = `
            <div class="error-content">
                <div class="error-icon">❌</div>
                <h3>${title}</h3>
                <p>A critical error occurred that prevents the application from functioning properly.</p>
                <details>
                    <summary>Error Details</summary>
                    <pre><code>${error.stack || error.message || error}</code></pre>
                </details>
                <div class="error-actions">
                    <button class="btn btn-primary" onclick="location.reload()">
                        Reload Application
                    </button>
                </div>
            </div>
        `;

        this.showModal('Critical Error', errorContent);
    }

    /**
     * Check if there are unsaved changes
     */
    hasUnsavedChanges() {
        // Check with all components if they have unsaved changes
        for (const component of this.components.values()) {
            if (component.hasUnsavedChanges?.()) {
                return true;
            }
        }
        return false;
    }

    /**
     * Register a component
     */
    registerComponent(name, component) {
        this.components.set(name, component);
        console.log(`Component registered: ${name}`);
    }

    /**
     * Get a registered component
     */
    getComponent(name) {
        return this.components.get(name);
    }

    /**
     * Destroy the application
     */
    destroy() {
        // Destroy all components
        for (const component of this.components.values()) {
            if (component.destroy) {
                component.destroy();
            }
        }
        this.components.clear();

        // Remove event listeners
        document.removeEventListener('keydown', this.handleKeyboardShortcuts);
        document.removeEventListener('visibilitychange', this.handleVisibilityChange);
        window.removeEventListener('online', this.handleOnline);
        window.removeEventListener('offline', this.handleOffline);

        // Clear state
        this.eventBus.clear();

        this.isInitialized = false;
        console.log('Chronos Engine destroyed');
    }
}

// Initialize application when DOM is ready
let chronosApp;

function initializeChronosApp() {
    chronosApp = new ChronosApplication();
    chronosApp.initialize();

    // Make available globally for debugging
    window.ChronosApp = chronosApp;
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeChronosApp);
} else {
    initializeChronosApp();
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ChronosApplication;
}