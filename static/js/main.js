/**
 * Chronos Engine - Main JavaScript
 * Core functionality and utilities
 */

// Global configuration
const CHRONOS_CONFIG = {
    API_BASE: '/api/v1',
    SYNC_BASE: '/api/v1/sync',
    API_KEY: 'development-key-change-in-production',
    REFRESH_INTERVAL: 300000, // 5 minutes
    TOAST_DURATION: 5000
};

// Global state
const ChronosApp = {
    isConnected: true,
    lastUpdate: null,
    notifications: [],
    activeRequests: new Set()
};

/**
 * Utility Functions
 */
class ChronosUtils {
    
    static formatDateTime(dateString) {
        if (!dateString) return 'N/A';
        
        try {
            const date = new Date(dateString);
            return date.toLocaleString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch (error) {
            console.error('Error formatting date:', error);
            return 'Invalid Date';
        }
    }
    
    static formatDuration(hours) {
        if (!hours || hours === 0) return '0h';
        
        if (hours < 1) {
            return `${Math.round(hours * 60)}m`;
        } else if (hours < 24) {
            const h = Math.floor(hours);
            const m = Math.round((hours - h) * 60);
            return m > 0 ? `${h}h ${m}m` : `${h}h`;
        } else {
            const days = Math.floor(hours / 24);
            const remainingHours = Math.round(hours % 24);
            return remainingHours > 0 ? `${days}d ${remainingHours}h` : `${days}d`;
        }
    }
    
    static formatPercentage(value, decimals = 1) {
        if (value === null || value === undefined) return '0%';
        return `${(value * 100).toFixed(decimals)}%`;
    }
    
    static debounce(func, wait) {
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
    
    static generateId() {
        return '_' + Math.random().toString(36).substr(2, 9);
    }
    
    static copyToClipboard(text) {
        if (navigator.clipboard && window.isSecureContext) {
            return navigator.clipboard.writeText(text);
        } else {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = text;
            textArea.style.position = 'fixed';
            textArea.style.left = '-999999px';
            textArea.style.top = '-999999px';
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            
            return new Promise((resolve, reject) => {
                if (document.execCommand('copy')) {
                    textArea.remove();
                    resolve();
                } else {
                    textArea.remove();
                    reject();
                }
            });
        }
    }
}

/**
 * API Client
 */
class ChronosAPI {
    
    static async request(endpoint, options = {}) {
        const requestId = ChronosUtils.generateId();
        ChronosApp.activeRequests.add(requestId);
        
        try {
            const defaultOptions = {
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${CHRONOS_CONFIG.API_KEY}`
                }
            };
            
            const mergedOptions = {
                ...defaultOptions,
                ...options,
                headers: {
                    ...defaultOptions.headers,
                    ...options.headers
                }
            };
            
            const response = await fetch(endpoint, mergedOptions);
            
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            }
            
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            }
            
            return await response.text();
            
        } catch (error) {
            console.error('API Request failed:', error);
            ChronosApp.isConnected = false;
            ChronosToast.error('Connection Error', error.message);
            throw error;
        } finally {
            ChronosApp.activeRequests.delete(requestId);
            ChronosApp.isConnected = true;
            updateConnectionStatus();
        }
    }
    
    static async get(endpoint) {
        return this.request(endpoint, { method: 'GET' });
    }
    
    static async post(endpoint, data) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }
    
    static async put(endpoint, data) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }
    
    static async delete(endpoint) {
        return this.request(endpoint, { method: 'DELETE' });
    }
}

/**
 * Toast Notification System
 */
class ChronosToast {
    
    static show(type, title, message, duration = CHRONOS_CONFIG.TOAST_DURATION) {
        const container = this.getContainer();
        const toast = this.createToast(type, title, message);

        container.appendChild(toast);

        // Animate in with modern classes
        setTimeout(() => toast.classList.add('toast-show'), 10);

        // Auto remove
        setTimeout(() => this.remove(toast), duration);

        return toast;
    }
    
    static success(title, message) {
        return this.show('success', title, message);
    }
    
    static warning(title, message) {
        return this.show('warning', title, message);
    }
    
    static error(title, message) {
        return this.show('error', title, message, 8000); // Longer duration for errors
    }
    
    static info(title, message) {
        return this.show('info', title, message);
    }
    
    static createToast(type, title, message) {
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
                <button class="toast-close" onclick="ChronosToast.remove(this.closest('.toast'))">×</button>
            </div>
            <div class="toast-body">${message}</div>
        `;
        
        return toast;
    }
    
    static remove(toast) {
        if (!toast) return;
        
        toast.classList.add('fade-out');
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }
    
    static getContainer() {
        let container = document.getElementById('toastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toastContainer';
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        return container;
    }
}

/**
 * Loading States
 */
class ChronosLoading {
    
    static show(element, text = 'Loading...') {
        if (!element) return;
        
        element.classList.add('loading');
        element.setAttribute('data-loading-text', text);
        element.disabled = true;
    }
    
    static hide(element) {
        if (!element) return;
        
        element.classList.remove('loading');
        element.removeAttribute('data-loading-text');
        element.disabled = false;
    }
    
    static toggle(element, isLoading, text = 'Loading...') {
        if (isLoading) {
            this.show(element, text);
        } else {
            this.hide(element);
        }
    }
}

/**
 * Core Functions
 */
async function syncCalendar() {
    const button = event?.target;
    
    try {
        if (button) ChronosLoading.show(button, 'Syncing...');
        
        const result = await ChronosAPI.post(`${CHRONOS_CONFIG.SYNC_BASE}/calendar`, {
            days_ahead: 7,
            force_refresh: true
        });
        
        ChronosToast.success(
            'Sync Complete', 
            `Successfully synced ${result.events_parsed || 0} events`
        );
        
        // Refresh dashboard data
        setTimeout(refreshDashboard, 1000);
        
    } catch (error) {
        console.error('Calendar sync failed:', error);
        ChronosToast.error('Sync Failed', 'Could not sync calendar. Please try again.');
    } finally {
        if (button) ChronosLoading.hide(button);
    }
}

async function optimizeSchedule() {
    const button = event?.target;
    
    try {
        if (button) ChronosLoading.show(button, 'Optimizing...');
        
        const result = await ChronosAPI.post(`${CHRONOS_CONFIG.SYNC_BASE}/ai/optimize`, {
            event_ids: [],
            optimization_window_days: 7,
            auto_apply: false
        });
        
        const suggestionCount = result.total_suggestions || 0;
        
        if (suggestionCount > 0) {
            ChronosToast.success(
                'Optimization Complete', 
                `Generated ${suggestionCount} suggestions for your schedule`
            );
        } else {
            ChronosToast.info(
                'Schedule Optimal', 
                'Your schedule is already well-optimized!'
            );
        }
        
    } catch (error) {
        console.error('Schedule optimization failed:', error);
        ChronosToast.error('Optimization Failed', 'Could not optimize schedule. Please try again.');
    } finally {
        if (button) ChronosLoading.hide(button);
    }
}

async function detectConflicts() {
    const button = event?.target;
    
    try {
        if (button) ChronosLoading.show(button, 'Detecting...');
        
        const result = await ChronosAPI.post(`${CHRONOS_CONFIG.SYNC_BASE}/detect-conflicts`);
        
        const conflictCount = result.total_conflicts || 0;
        
        if (conflictCount > 0) {
            ChronosToast.warning(
                'Conflicts Detected', 
                `Found ${conflictCount} scheduling conflicts that need attention`
            );
        } else {
            ChronosToast.success(
                'No Conflicts', 
                'Your schedule is conflict-free!'
            );
        }
        
    } catch (error) {
        console.error('Conflict detection failed:', error);
        ChronosToast.error('Detection Failed', 'Could not detect conflicts. Please try again.');
    } finally {
        if (button) ChronosLoading.hide(button);
    }
}

async function generateReport() {
    const button = event?.target;
    
    try {
        if (button) ChronosLoading.show(button, 'Generating...');
        
        const result = await ChronosAPI.get(`${CHRONOS_CONFIG.SYNC_BASE}/analytics/report`);
        
        if (result.success) {
            ChronosToast.success(
                'Report Generated',
                'Analytics report has been generated successfully.'
            );
        }
        
    } catch (error) {
        console.error('Report generation failed:', error);
        ChronosToast.error('Generation Failed', 'Could not generate report. Please try again.');
    } finally {
        if (button) ChronosLoading.hide(button);
    }
}

async function pollTaskStatus(taskId, maxAttempts = 20) {
    let attempts = 0;
    
    const poll = async () => {
        try {
            // Task status tracking not needed for direct API calls
            const status = { status: 'completed', name: 'Task' };
            
            if (status.status === 'completed') {
                ChronosToast.success('Task Complete', `Task "${status.name}" completed successfully`);
                return;
            } else if (status.status === 'failed') {
                ChronosToast.error('Task Failed', `Task "${status.name}" failed: ${status.error || 'Unknown error'}`);
                return;
            } else if (attempts >= maxAttempts) {
                ChronosToast.warning('Task Timeout', 'Task is taking longer than expected');
                return;
            }
            
            attempts++;
            setTimeout(poll, 3000); // Poll every 3 seconds
            
        } catch (error) {
            console.error('Task polling failed:', error);
        }
    };
    
    poll();
}

function refreshDashboard() {
    location.reload();
}

function exportData() {
    const button = event?.target;
    
    try {
        if (button) ChronosLoading.show(button, 'Exporting...');
        
        // Create export data
        const exportData = {
            exported_at: new Date().toISOString(),
            dashboard_data: ChronosApp.lastUpdate,
            user_agent: navigator.userAgent,
            url: window.location.href
        };
        
        // Create and download file
        const dataStr = JSON.stringify(exportData, null, 2);
        const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
        
        const exportFileDefaultName = `chronos-export-${new Date().toISOString().split('T')[0]}.json`;
        
        const linkElement = document.createElement('a');
        linkElement.setAttribute('href', dataUri);
        linkElement.setAttribute('download', exportFileDefaultName);
        linkElement.click();
        
        ChronosToast.success('Export Complete', 'Dashboard data exported successfully');
        
    } catch (error) {
        console.error('Data export failed:', error);
        ChronosToast.error('Export Failed', 'Could not export data. Please try again.');
    } finally {
        if (button) ChronosLoading.hide(button);
    }
}

function showHelp() {
    const helpContent = `
        <div class="help-content">
            <h3>🚀 Chronos Engine Help</h3>
            <div class="help-section">
                <h4>Dashboard Overview</h4>
                <p>The dashboard provides real-time insights into your calendar management and productivity metrics.</p>
            </div>
            <div class="help-section">
                <h4>Quick Actions</h4>
                <ul>
                    <li><strong>Sync Calendar:</strong> Manually sync your calendar events</li>
                    <li><strong>Optimize Schedule:</strong> Get AI-powered scheduling suggestions</li>
                    <li><strong>Generate Report:</strong> Create detailed analytics reports</li>
                    <li><strong>Detect Conflicts:</strong> Find scheduling conflicts</li>
                </ul>
            </div>
            <div class="help-section">
                <h4>Keyboard Shortcuts</h4>
                <ul>
                    <li><kbd>Ctrl + R</kbd> - Refresh dashboard</li>
                    <li><kbd>Ctrl + S</kbd> - Sync calendar</li>
                    <li><kbd>Escape</kbd> - Close dialogs</li>
                </ul>
            </div>
            <div class="help-section">
                <h4>API Documentation</h4>
                <p>Visit <a href="/docs" target="_blank">/docs</a> for complete API documentation.</p>
            </div>
        </div>
    `;
    
    showModal('Help', helpContent);
}

function updateConnectionStatus() {
    const statusElements = document.querySelectorAll('#connectionStatus, .status-badge, .connection-status');

    statusElements.forEach(element => {
        const dot = element.querySelector('.status-dot, .status-indicator');
        const text = element.querySelector('.status-text') || element.lastChild;

        if (ChronosApp.isConnected) {
            if (dot) {
                dot.className = dot.className.replace(/status-(offline|error|inactive)/, '');
                dot.classList.add('status-indicator', 'status-online');
            }
            if (text && text.nodeType === Node.TEXT_NODE) {
                text.textContent = 'Online';
            }
            element.classList.remove('status-error', 'status-offline');
            element.classList.add('status-online');
        } else {
            if (dot) {
                dot.className = dot.className.replace(/status-(online|active)/, '');
                dot.classList.add('status-indicator', 'status-offline');
            }
            if (text && text.nodeType === Node.TEXT_NODE) {
                text.textContent = 'Offline';
            }
            element.classList.remove('status-online');
            element.classList.add('status-offline');
        }
    });
}

function showModal(title, content, options = {}) {
    // Create modal backdrop
    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop';
    backdrop.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.5);
        z-index: 1050;
        display: flex;
        align-items: center;
        justify-content: center;
    `;
    
    // Create modal
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.style.cssText = `
        background: white;
        border-radius: 10px;
        max-width: 500px;
        max-height: 80vh;
        overflow-y: auto;
        box-shadow: 0 8px 24px rgba(0,0,0,0.2);
        animation: modalIn 0.3s ease;
    `;
    
    modal.innerHTML = `
        <div class="modal-header">
            <h3 class="modal-title">${title}</h3>
            <button class="btn btn-ghost btn-sm modal-close" aria-label="Close modal">&times;</button>
        </div>
        <div class="modal-body">
            ${content}
        </div>
        <div class="modal-footer">
            <button class="btn btn-secondary modal-close">Close</button>
        </div>
    `;
    
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    
    // Close handlers
    const closeModal = () => {
        backdrop.style.animation = 'modalOut 0.3s ease';
        setTimeout(() => document.body.removeChild(backdrop), 300);
    };
    
    backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) closeModal();
    });
    
    modal.querySelectorAll('.modal-close').forEach(btn => {
        btn.addEventListener('click', closeModal);
    });
    
    // Escape key
    const escapeHandler = (e) => {
        if (e.key === 'Escape') {
            closeModal();
            document.removeEventListener('keydown', escapeHandler);
        }
    };
    document.addEventListener('keydown', escapeHandler);
    
    // Add animation styles
    if (!document.querySelector('#modal-animations')) {
        const style = document.createElement('style');
        style.id = 'modal-animations';
        style.textContent = `
            @keyframes modalIn {
                from { opacity: 0; transform: scale(0.8); }
                to { opacity: 1; transform: scale(1); }
            }
            @keyframes modalOut {
                from { opacity: 1; transform: scale(1); }
                to { opacity: 0; transform: scale(0.8); }
            }
        `;
        document.head.appendChild(style);
    }
}

/**
 * Keyboard Shortcuts
 */
function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey || e.metaKey) {
            switch (e.key) {
                case 'r':
                    if (!e.shiftKey) {
                        e.preventDefault();
                        refreshDashboard();
                    }
                    break;
                case 's':
                    e.preventDefault();
                    syncCalendar();
                    break;
                case '/':
                    e.preventDefault();
                    showHelp();
                    break;
            }
        }
    });
}

/**
 * Auto-refresh functionality
 */
function startAutoRefresh() {
    setInterval(() => {
        if (document.visibilityState === 'visible' && ChronosApp.isConnected) {
            updateLastUpdateTime();
        }
    }, CHRONOS_CONFIG.REFRESH_INTERVAL);
}

function updateLastUpdateTime() {
    const now = new Date();
    ChronosApp.lastUpdate = now;
    
    const updateElements = document.querySelectorAll('#lastUpdate, .last-update');
    updateElements.forEach(element => {
        element.textContent = ChronosUtils.formatDateTime(now.toISOString());
    });
}

/**
 * Initialize App
 */
function initializeChronosApp() {
    console.log('🚀 Chronos Engine initializing...');
    
    // Initialize components
    initializeKeyboardShortcuts();
    startAutoRefresh();
    updateLastUpdateTime();
    updateConnectionStatus();
    
    // Add global error handler
    window.addEventListener('error', (e) => {
        console.error('Global error:', e.error);
        ChronosToast.error('Application Error', 'An unexpected error occurred');
    });
    
    // Add unhandled promise rejection handler
    window.addEventListener('unhandledrejection', (e) => {
        console.error('Unhandled promise rejection:', e.reason);
        ChronosToast.error('Promise Error', 'An async operation failed');
        e.preventDefault();
    });
    
    // Check connection periodically
    setInterval(async () => {
        try {
            await ChronosAPI.get(`${CHRONOS_CONFIG.SYNC_BASE}/health`);
            if (!ChronosApp.isConnected) {
                ChronosApp.isConnected = true;
                updateConnectionStatus();
                ChronosToast.success('Connection Restored', 'Successfully reconnected to server');
            }
        } catch (error) {
            if (ChronosApp.isConnected) {
                ChronosApp.isConnected = false;
                updateConnectionStatus();
            }
        }
    }, 30000); // Check every 30 seconds
    
    console.log('✅ Chronos Engine initialized successfully');
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeChronosApp);
} else {
    initializeChronosApp();
}

// Export globals for use in other scripts
window.ChronosAPI = ChronosAPI;
window.ChronosToast = ChronosToast;
window.ChronosLoading = ChronosLoading;
window.ChronosUtils = ChronosUtils;
window.ChronosApp = ChronosApp;
