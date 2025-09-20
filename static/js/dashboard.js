// Chronos Dashboard - Enhanced JavaScript Integration
// n8n Style Dashboard mit erweiterten Funktionen

class ChronosDashboard {
    constructor() {
        this.config = {
            refreshInterval: 30000, // 30 Sekunden
            apiBaseUrl: '/api',
            wsUrl: window.location.protocol === 'https:' ? 'wss:' : 'ws:' + '//' + window.location.host + '/ws'
        };

        this.state = {
            isConnected: false,
            lastUpdate: null,
            metrics: {},
            events: [],
            syncStatus: {},
            filters: {
                search: '',
                sort: 'date',
                type: 'all'
            }
        };

        this.websocket = null;
        this.refreshTimer = null;
    }

    async initialize() {
        console.log('🚀 Chronos Dashboard initializing...');

        // Load initial data
        await this.loadDashboardData();

        // Setup event listeners
        this.setupEventListeners();

        // Initialize WebSocket connection
        this.initializeWebSocket();

        // Start auto-refresh
        this.startAutoRefresh();

        // Load saved preferences
        this.loadUserPreferences();

        console.log('✅ Chronos Dashboard initialized successfully');
    }

    setupEventListeners() {
        // Sidebar toggle
        const sidebarToggle = document.querySelector('[onclick="toggleSidebar()"]');
        if (sidebarToggle) {
            sidebarToggle.addEventListener('click', this.toggleSidebar.bind(this));
        }

        // Search functionality
        const searchInput = document.getElementById('searchInput');
        if (searchInput) {
            searchInput.addEventListener('input', this.debounce(this.handleSearch.bind(this), 300));
        }

        // Filter controls
        const sortFilter = document.getElementById('sortFilter');
        if (sortFilter) {
            sortFilter.addEventListener('change', this.handleSortChange.bind(this));
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', this.handleKeyboardShortcuts.bind(this));

        // Window visibility for auto-refresh
        document.addEventListener('visibilitychange', this.handleVisibilityChange.bind(this));
    }

    initializeWebSocket() {
        if (!this.config.wsUrl) return;

        try {
            this.websocket = new WebSocket(this.config.wsUrl);

            this.websocket.onopen = () => {
                console.log('🔌 WebSocket connected');
                this.updateConnectionStatus(true);
            };

            this.websocket.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            };

            this.websocket.onclose = () => {
                console.log('🔌 WebSocket disconnected');
                this.updateConnectionStatus(false);
                // Reconnect after 5 seconds
                setTimeout(() => this.initializeWebSocket(), 5000);
            };

            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.updateConnectionStatus(false);
            };
        } catch (error) {
            console.error('Failed to initialize WebSocket:', error);
        }
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'metrics_update':
                this.updateMetrics(data.metrics);
                break;
            case 'event_update':
                this.refreshEventsList();
                break;
            case 'sync_status':
                this.updateSyncStatus(data.sync_status);
                break;
            case 'notification':
                this.showToast(data.title, data.message, data.level);
                break;
        }
    }

    async loadDashboardData() {
        try {
            this.showLoading();

            const [metricsResponse, eventsResponse, syncResponse] = await Promise.all([
                fetch(`${this.config.apiBaseUrl}/dashboard/metrics`),
                fetch(`${this.config.apiBaseUrl}/events?limit=10`),
                fetch(`${this.config.apiBaseUrl}/sync/status`)
            ]);

            const metrics = await metricsResponse.json();
            const events = await eventsResponse.json();
            const syncStatus = await syncResponse.json();

            this.state.metrics = metrics;
            this.state.events = events.events || [];
            this.state.syncStatus = syncStatus;
            this.state.lastUpdate = new Date();

            this.updateMetrics(metrics);
            this.updateEventsList(this.state.events);
            this.updateSyncStatus(syncStatus);
            this.updateLastUpdateTime();

        } catch (error) {
            console.error('Error loading dashboard data:', error);
            this.showToast('Fehler', 'Dashboard-Daten konnten nicht geladen werden', 'error');
        } finally {
            this.hideLoading();
        }
    }

    updateMetrics(metrics) {
        const elements = {
            totalEvents: document.getElementById('totalEvents'),
            productivityRate: document.getElementById('productivityRate'),
            timeSaved: document.getElementById('timeSaved'),
            completedTasks: document.getElementById('completedTasks')
        };

        if (elements.totalEvents) {
            this.animateCounter(elements.totalEvents, metrics.total_events || 0);
        }

        if (elements.productivityRate) {
            this.animateCounter(elements.productivityRate, metrics.completion_rate || 0, '%');
        }

        if (elements.timeSaved) {
            this.animateCounter(elements.timeSaved, metrics.total_hours || 0, 'h');
        }

        if (elements.completedTasks) {
            this.animateCounter(elements.completedTasks, metrics.completed_tasks || 0);
        }

        // Update change indicators
        this.updateChangeIndicators(metrics);
    }

    updateChangeIndicators(metrics) {
        const changes = {
            eventsChange: metrics.events_change || 0,
            productivityChange: metrics.productivity_change || 0,
            timeSavedChange: metrics.time_saved_change || 0,
            tasksChange: metrics.tasks_change || 0
        };

        Object.entries(changes).forEach(([key, value]) => {
            const element = document.getElementById(key);
            if (element) {
                element.className = `metric-change ${value > 0 ? 'positive' : value < 0 ? 'negative' : 'neutral'}`;
                const arrow = value > 0 ? '↗️' : value < 0 ? '↘️' : '→';
                const sign = value > 0 ? '+' : '';
                element.textContent = `${arrow} ${sign}${value}${key.includes('productivity') ? '%' : ''}`;
            }
        });
    }

    updateEventsList(events) {
        const eventsList = document.getElementById('eventsList');
        const eventCount = document.getElementById('eventCount');

        if (eventCount) {
            eventCount.textContent = events.length;
        }

        if (!eventsList) return;

        eventsList.innerHTML = events.map(event => this.createEventListItem(event)).join('');
    }

    createEventListItem(event) {
        const priorityColors = {
            'URGENT': 'danger',
            'HIGH': 'warning',
            'MEDIUM': 'info',
            'LOW': 'success'
        };

        const typeIcons = {
            'MEETING': '📅',
            'TASK': '📋',
            'DEADLINE': '🎯',
            'APPOINTMENT': '👥',
            'REMINDER': '⏰'
        };

        const statusIndicators = {
            'ACTIVE': 'active',
            'COMPLETED': 'success',
            'PENDING': 'warning',
            'CANCELLED': 'error'
        };

        return `
            <div class="list-item" data-event-id="${event.id}">
                <div class="list-item-info">
                    <h4 class="list-item-title">
                        ${typeIcons[event.event_type] || '📅'} ${event.title}
                        <span class="badge bg-${priorityColors[event.priority] || 'secondary'}">${event.event_type}</span>
                    </h4>
                    <p class="list-item-meta">
                        ${this.formatDateTime(event.start_time)} |
                        ${event.location || 'Kein Ort'} |
                        ${event.priority} Priorität
                    </p>
                </div>
                <div class="list-item-actions">
                    <span class="status-indicator ${statusIndicators[event.status] || 'inactive'}"></span>
                    <span class="status-text">${this.translateStatus(event.status)}</span>
                    <button class="btn btn-secondary btn-sm" onclick="editEvent('${event.id}')">
                        Bearbeiten
                    </button>
                </div>
            </div>
        `;
    }

    updateSyncStatus(syncStatus) {
        const elements = {
            lastSyncTime: document.getElementById('lastSyncTime'),
            syncedEvents: document.getElementById('syncedEvents'),
            apiQuota: document.getElementById('apiQuota'),
            syncStatus: document.getElementById('syncStatus')
        };

        if (elements.lastSyncTime) {
            elements.lastSyncTime.textContent = this.formatRelativeTime(syncStatus.last_update);
        }

        if (elements.syncedEvents) {
            elements.syncedEvents.textContent = syncStatus.total_events || 0;
        }

        if (elements.apiQuota) {
            const used = syncStatus.quota_used || 0;
            const limit = syncStatus.quota_limit || 100000;
            elements.apiQuota.textContent = `${used.toLocaleString()} / ${limit.toLocaleString()}`;
        }

        if (elements.syncStatus) {
            const isConnected = syncStatus.status === 'connected';
            elements.syncStatus.innerHTML = `
                <span class="status-indicator ${isConnected ? 'active' : 'inactive'}"></span>
                ${isConnected ? 'Verbunden' : 'Getrennt'}
            `;
        }
    }

    // Event Handlers
    toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        sidebar.classList.toggle('collapsed');
        localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
    }

    handleSearch(event) {
        this.state.filters.search = event.target.value;
        this.filterEvents();
    }

    handleSortChange(event) {
        this.state.filters.sort = event.target.value;
        this.sortEvents();
    }

    handleKeyboardShortcuts(event) {
        if (event.ctrlKey || event.metaKey) {
            switch (event.key) {
                case 'r':
                    if (!event.shiftKey) {
                        event.preventDefault();
                        this.refreshDashboard();
                    }
                    break;
                case 's':
                    event.preventDefault();
                    this.syncCalendar();
                    break;
                case '/':
                    event.preventDefault();
                    document.getElementById('searchInput')?.focus();
                    break;
                case 'k':
                    event.preventDefault();
                    this.toggleSidebar();
                    break;
            }
        }
    }

    handleVisibilityChange() {
        if (document.hidden) {
            this.stopAutoRefresh();
        } else {
            this.startAutoRefresh();
            this.refreshDashboard();
        }
    }

    // Sync Functions
    async syncCalendar(type = 'incremental') {
        try {
            this.showToast('Synchronisation gestartet', 'Kalender wird synchronisiert...', 'info');

            const response = await fetch(`${this.config.apiBaseUrl}/sync/${type}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            const result = await response.json();

            if (response.ok) {
                this.showToast('Sync erfolgreich', result.message || 'Kalender wurde erfolgreich synchronisiert', 'success');
                await this.loadDashboardData();
            } else {
                throw new Error(result.error || 'Synchronisation fehlgeschlagen');
            }
        } catch (error) {
            console.error('Sync error:', error);
            this.showToast('Sync Fehler', error.message, 'error');
        }
    }

    async triggerFullSync() {
        this.showLoading();
        await this.syncCalendar('full');
        this.hideLoading();
    }

    async triggerIncrementalSync() {
        await this.syncCalendar('incremental');
    }

    // Utility Functions
    animateCounter(element, targetValue, suffix = '') {
        const startValue = parseInt(element.textContent) || 0;
        const increment = (targetValue - startValue) / 20;
        let currentValue = startValue;

        const timer = setInterval(() => {
            currentValue += increment;
            if ((increment > 0 && currentValue >= targetValue) ||
                (increment < 0 && currentValue <= targetValue)) {
                currentValue = targetValue;
                clearInterval(timer);
            }
            element.textContent = Math.round(currentValue) + suffix;
        }, 50);
    }

    formatDateTime(dateString) {
        if (!dateString) return 'Kein Datum';

        try {
            const date = new Date(dateString);
            const now = new Date();
            const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            const eventDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());

            const dayDiff = Math.floor((eventDate - today) / (1000 * 60 * 60 * 24));

            let dayText;
            if (dayDiff === 0) dayText = 'Heute';
            else if (dayDiff === 1) dayText = 'Morgen';
            else if (dayDiff === -1) dayText = 'Gestern';
            else if (dayDiff > 1 && dayDiff <= 7) dayText = `In ${dayDiff} Tagen`;
            else dayText = date.toLocaleDateString('de-DE');

            const timeText = date.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });

            return `${dayText}, ${timeText}`;
        } catch {
            return 'Ungültiges Datum';
        }
    }

    formatRelativeTime(dateString) {
        if (!dateString) return 'Unbekannt';

        try {
            const date = new Date(dateString);
            const now = new Date();
            const diffMs = now - date;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMins / 60);
            const diffDays = Math.floor(diffHours / 24);

            if (diffMins < 1) return 'gerade eben';
            if (diffMins < 60) return `vor ${diffMins} Min`;
            if (diffHours < 24) return `vor ${diffHours} Std`;
            if (diffDays < 7) return `vor ${diffDays} Tagen`;
            return date.toLocaleDateString('de-DE');
        } catch {
            return 'Unbekannt';
        }
    }

    translateStatus(status) {
        const translations = {
            'ACTIVE': 'Aktiv',
            'COMPLETED': 'Abgeschlossen',
            'PENDING': 'Ausstehend',
            'CANCELLED': 'Abgebrochen',
            'SCHEDULED': 'Geplant'
        };
        return translations[status] || status;
    }

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

    // Filter and Sort Functions
    filterEvents() {
        const searchTerm = this.state.filters.search.toLowerCase();
        const filteredEvents = this.state.events.filter(event =>
            event.title.toLowerCase().includes(searchTerm) ||
            event.description?.toLowerCase().includes(searchTerm) ||
            event.location?.toLowerCase().includes(searchTerm)
        );

        this.updateEventsList(filteredEvents);
    }

    sortEvents() {
        const sortBy = this.state.filters.sort;
        let sortedEvents = [...this.state.events];

        switch (sortBy) {
            case 'date':
                sortedEvents.sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
                break;
            case 'priority':
                const priorityOrder = { 'URGENT': 4, 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1 };
                sortedEvents.sort((a, b) => (priorityOrder[b.priority] || 0) - (priorityOrder[a.priority] || 0));
                break;
            case 'type':
                sortedEvents.sort((a, b) => a.event_type.localeCompare(b.event_type));
                break;
            case 'status':
                sortedEvents.sort((a, b) => a.status.localeCompare(b.status));
                break;
        }

        this.updateEventsList(sortedEvents);
    }

    // UI Helper Functions
    showLoading() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) overlay.style.display = 'flex';
    }

    hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) overlay.style.display = 'none';
    }

    showToast(title, message, type = 'info') {
        const toastContainer = document.getElementById('toastContainer');
        if (!toastContainer) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        const toastId = 'toast_' + Date.now();
        toast.id = toastId;

        toast.innerHTML = `
            <div class="toast-header">
                <h4 class="toast-title">${title}</h4>
                <button class="modal-close" onclick="document.getElementById('${toastId}').remove()">×</button>
            </div>
            <div class="toast-body">${message}</div>
        `;

        toastContainer.appendChild(toast);

        // Auto-remove nach 5 Sekunden
        setTimeout(() => {
            if (document.getElementById(toastId)) {
                document.getElementById(toastId).remove();
            }
        }, 5000);
    }

    updateConnectionStatus(isConnected) {
        this.state.isConnected = isConnected;

        // Update UI indicators
        const indicators = document.querySelectorAll('.connection-status');
        indicators.forEach(indicator => {
            indicator.className = `status-indicator ${isConnected ? 'active' : 'inactive'}`;
        });
    }

    updateLastUpdateTime() {
        const now = new Date();
        this.state.lastUpdate = now;

        const updateElements = document.querySelectorAll('.last-update');
        updateElements.forEach(element => {
            element.textContent = this.formatRelativeTime(now.toISOString());
        });
    }

    // Auto-refresh functionality
    startAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
        }

        this.refreshTimer = setInterval(() => {
            if (!document.hidden && this.state.isConnected) {
                this.loadDashboardData();
            }
        }, this.config.refreshInterval);
    }

    stopAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
    }

    refreshDashboard() {
        this.loadDashboardData();
    }

    // User Preferences
    loadUserPreferences() {
        // Load sidebar state
        const sidebarCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
        const sidebar = document.getElementById('sidebar');
        if (sidebarCollapsed && sidebar) {
            sidebar.classList.add('collapsed');
        }

        // Load other preferences
        const savedFilters = localStorage.getItem('chronos_filters');
        if (savedFilters) {
            try {
                this.state.filters = { ...this.state.filters, ...JSON.parse(savedFilters) };
                this.applyFilters();
            } catch (error) {
                console.warn('Failed to load saved filters:', error);
            }
        }
    }

    saveUserPreferences() {
        localStorage.setItem('chronos_filters', JSON.stringify(this.state.filters));
    }

    applyFilters() {
        // Apply search filter
        const searchInput = document.getElementById('searchInput');
        if (searchInput) {
            searchInput.value = this.state.filters.search;
        }

        // Apply sort filter
        const sortFilter = document.getElementById('sortFilter');
        if (sortFilter) {
            sortFilter.value = this.state.filters.sort;
        }

        // Apply filters
        this.filterEvents();
        this.sortEvents();
    }

    // Export functionality
    async exportData(format = 'json') {
        try {
            this.showToast('Export gestartet', 'Daten werden exportiert...', 'info');

            const response = await fetch(`${this.config.apiBaseUrl}/export/${format}`, {
                method: 'GET',
                headers: {
                    'Accept': format === 'json' ? 'application/json' : 'text/csv'
                }
            });

            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `chronos_data_${new Date().toISOString().split('T')[0]}.${format}`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);

                this.showToast('Export erfolgreich', 'Daten wurden erfolgreich exportiert', 'success');
            } else {
                throw new Error('Export fehlgeschlagen');
            }
        } catch (error) {
            console.error('Export error:', error);
            this.showToast('Export Fehler', error.message, 'error');
        }
    }

    // Cleanup
    destroy() {
        this.stopAutoRefresh();

        if (this.websocket) {
            this.websocket.close();
        }

        this.saveUserPreferences();
    }
}

// Global Functions (für HTML onclick handlers)
let dashboardInstance = null;

function initializeChronosApp() {
    dashboardInstance = new ChronosDashboard();
    dashboardInstance.initialize();

    // Setup global functions
    window.toggleSidebar = () => dashboardInstance.toggleSidebar();
    window.refreshDashboard = () => dashboardInstance.refreshDashboard();
    window.syncCalendar = () => dashboardInstance.triggerIncrementalSync();
    window.triggerFullSync = () => dashboardInstance.triggerFullSync();
    window.triggerIncrementalSync = () => dashboardInstance.triggerIncrementalSync();
    window.exportData = () => dashboardInstance.exportData('json');
    window.toggleView = () => {
        dashboardInstance.showToast('Ansicht gewechselt', 'Ansichtsmodus wurde geändert', 'info');
    };

    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
        if (dashboardInstance) {
            dashboardInstance.destroy();
        }
    });
}

// Event specific functions
function editEvent(eventId) {
    dashboardInstance.showToast('Event bearbeiten', `Event ${eventId} wird bearbeitet...`, 'info');
    // Hier würde das Event-Edit Modal geöffnet werden
}

// Theme toggle function
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';

    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('chronos_theme', newTheme);

    dashboardInstance.showToast('Theme geändert', `${newTheme === 'dark' ? 'Dunkles' : 'Helles'} Theme aktiviert`, 'info');
}

// Load saved theme
function loadSavedTheme() {
    const savedTheme = localStorage.getItem('chronos_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
}

// Initialize theme on page load
document.addEventListener('DOMContentLoaded', () => {
    loadSavedTheme();
});

// Additional utility functions for the dashboard
const ChronosUtils = {
    // Format functions
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    formatDuration(minutes) {
        const hours = Math.floor(minutes / 60);
        const mins = minutes % 60;
        if (hours > 0) {
            return `${hours}h ${mins}m`;
        }
        return `${mins}m`;
    },

    // Color functions
    getPriorityColor(priority) {
        const colors = {
            'URGENT': '#ff4757',
            'HIGH': '#ffb347',
            'MEDIUM': '#17a2b8',
            'LOW': '#00c851'
        };
        return colors[priority] || '#6c757d';
    },

    getTypeIcon(type) {
        const icons = {
            'MEETING': '📅',
            'TASK': '📋',
            'DEADLINE': '🎯',
            'APPOINTMENT': '👥',
            'REMINDER': '⏰',
            'EVENT': '🗓️'
        };
        return icons[type] || '📅';
    },

    // Validation functions
    isValidEmail(email) {
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(email);
    },

    isValidUrl(url) {
        try {
            new URL(url);
            return true;
        } catch {
            return false;
        }
    },

    // Local storage helpers
    setStorageItem(key, value) {
        try {
            localStorage.setItem(`chronos_${key}`, JSON.stringify(value));
        } catch (error) {
            console.warn('Failed to save to localStorage:', error);
        }
    },

    getStorageItem(key, defaultValue = null) {
        try {
            const item = localStorage.getItem(`chronos_${key}`);
            return item ? JSON.parse(item) : defaultValue;
        } catch (error) {
            console.warn('Failed to read from localStorage:', error);
            return defaultValue;
        }
    }
};

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ChronosDashboard, ChronosUtils };
}