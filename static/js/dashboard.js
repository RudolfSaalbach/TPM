// Chronos Dashboard - Enhanced JavaScript Integration
// n8n Style Dashboard mit erweiterten Funktionen

class ChronosDashboard {
    constructor() {
        this.config = {
            refreshInterval: 30000, // 30 Sekunden
            apiBaseUrl: '/api/v1',
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
                fetch(`/api/v1/dashboard-data`),
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
                        <span class="icon">✏️</span>
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
        toast.className = `toast toast-${type}`;

        const toastId = 'toast_' + Date.now();
        toast.id = toastId;

        const icons = {
            success: '✅',
            warning: '⚠️',
            error: '❌',
            info: 'ℹ️'
        };

        toast.innerHTML = `
            <div class="toast-header">
                <span class="toast-icon">${icons[type] || 'ℹ️'}</span>
                <h4 class="toast-title">${title}</h4>
                <button class="btn btn-ghost btn-sm modal-close" onclick="document.getElementById('${toastId}').remove()">×</button>
            </div>
            <div class="toast-body">${message}</div>
        `;

        toastContainer.appendChild(toast);

        // Animate in with modern classes
        setTimeout(() => toast.classList.add('toast-show'), 10);

        // Auto-remove nach 5 Sekunden
        setTimeout(() => {
            if (document.getElementById(toastId)) {
                const toastEl = document.getElementById(toastId);
                toastEl.classList.add('toast-hide');
                setTimeout(() => toastEl.remove(), 300);
            }
        }, 5000);
    }

    updateConnectionStatus(isConnected) {
        this.state.isConnected = isConnected;

        // Update UI indicators with modern classes
        const indicators = document.querySelectorAll('.connection-status, .status-indicator');
        indicators.forEach(indicator => {
            indicator.className = indicator.className.replace(/status-(active|inactive|online|offline)/, '');
            indicator.classList.add('status-indicator', isConnected ? 'status-online' : 'status-offline');
        });

        // Update text elements
        const statusTexts = document.querySelectorAll('.status-text');
        statusTexts.forEach(text => {
            text.textContent = isConnected ? 'Online' : 'Offline';
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

            // Local export as fallback
            const data = {
                events: this.state.events,
                metrics: this.state.metrics,
                exported_at: new Date().toISOString()
            };

            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `chronos_data_${new Date().toISOString().split('T')[0]}.${format}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);

            this.showToast('Export erfolgreich', 'Daten wurden erfolgreich exportiert', 'success');
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
async function editEvent(eventId) {
    try {
        // Fetch event details
        const response = await fetch(`/api/v1/events/${eventId}`, {
            headers: {
                'Authorization': `Bearer ${window.CHRONOS_CONFIG.API_KEY}`
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const event = await response.json();

        // Parse start/end times
        const startDate = new Date(event.start_time);
        const endDate = new Date(event.end_time);

        const formattedDate = startDate.toISOString().split('T')[0];
        const startTime = startDate.toTimeString().slice(0, 5);
        const endTime = endDate.toTimeString().slice(0, 5);

        // Show edit modal with pre-filled data
        showModal('edit-event-modal', 'Event bearbeiten', `
            <form id="editEventForm">
                <input type="hidden" name="eventId" value="${eventId}">
                <div style="display: flex; flex-direction: column; gap: var(--space-4);">
                    <div>
                        <label for="editEventTitle" style="display: block; margin-bottom: var(--space-2); font-weight: var(--font-weight-medium);">Titel</label>
                        <input type="text" id="editEventTitle" name="title" value="${event.summary || ''}" style="width: 100%; padding: var(--space-3); border: 1px solid var(--border-base); border-radius: var(--radius-md);" required>
                    </div>
                    <div>
                        <label for="editEventDate" style="display: block; margin-bottom: var(--space-2); font-weight: var(--font-weight-medium);">Datum</label>
                        <input type="date" id="editEventDate" name="date" value="${formattedDate}" style="width: 100%; padding: var(--space-3); border: 1px solid var(--border-base); border-radius: var(--radius-md);" required>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3);">
                        <div>
                            <label for="editEventTime" style="display: block; margin-bottom: var(--space-2); font-weight: var(--font-weight-medium);">Startzeit</label>
                            <input type="time" id="editEventTime" name="time" value="${startTime}" style="width: 100%; padding: var(--space-3); border: 1px solid var(--border-base); border-radius: var(--radius-md);" required>
                        </div>
                        <div>
                            <label for="editEventEndTime" style="display: block; margin-bottom: var(--space-2); font-weight: var(--font-weight-medium);">Endzeit</label>
                            <input type="time" id="editEventEndTime" name="endTime" value="${endTime}" style="width: 100%; padding: var(--space-3); border: 1px solid var(--border-base); border-radius: var(--radius-md);" required>
                        </div>
                    </div>
                    <div>
                        <label for="editEventDescription" style="display: block; margin-bottom: var(--space-2); font-weight: var(--font-weight-medium);">Beschreibung</label>
                        <textarea id="editEventDescription" name="description" rows="3" style="width: 100%; padding: var(--space-3); border: 1px solid var(--border-base); border-radius: var(--radius-md); resize: vertical;">${event.description || ''}</textarea>
                    </div>
                    <div>
                        <label for="editEventLocation" style="display: block; margin-bottom: var(--space-2); font-weight: var(--font-weight-medium);">Ort</label>
                        <input type="text" id="editEventLocation" name="location" value="${event.location || ''}" style="width: 100%; padding: var(--space-3); border: 1px solid var(--border-base); border-radius: var(--radius-md);">
                    </div>
                    <div>
                        <label for="editEventPriority" style="display: block; margin-bottom: var(--space-2); font-weight: var(--font-weight-medium);">Priorität</label>
                        <select id="editEventPriority" name="priority" style="width: 100%; padding: var(--space-3); border: 1px solid var(--border-base); border-radius: var(--radius-md);">
                            <option value="low" ${event.priority === 'low' ? 'selected' : ''}>Niedrig</option>
                            <option value="medium" ${event.priority === 'medium' ? 'selected' : ''}>Mittel</option>
                            <option value="high" ${event.priority === 'high' ? 'selected' : ''}>Hoch</option>
                            <option value="urgent" ${event.priority === 'urgent' ? 'selected' : ''}>Dringend</option>
                        </select>
                    </div>
                </div>
            </form>
        `, '<button class="btn btn-secondary" onclick="closeModal()">Abbrechen</button><button class="btn btn-danger" onclick="deleteEvent(\'' + eventId + '\')">Löschen</button><button class="btn btn-primary" onclick="updateEvent()">Aktualisieren</button>');

    } catch (error) {
        console.error('Error loading event for edit:', error);
        dashboardInstance.showToast('Fehler', 'Event konnte nicht geladen werden: ' + error.message, 'error');
    }
}

// Update and Delete functions
async function updateEvent() {
    const form = document.getElementById('editEventForm');
    if (form && form.checkValidity()) {
        const formData = new FormData(form);
        const eventId = formData.get('eventId');

        const eventData = {
            summary: formData.get('title'),
            start_time: formData.get('date') + 'T' + formData.get('time'),
            end_time: formData.get('date') + 'T' + formData.get('endTime'),
            description: formData.get('description') || '',
            location: formData.get('location') || '',
            priority: formData.get('priority')
        };

        try {
            const response = await fetch(`/api/v1/events/${eventId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${window.CHRONOS_CONFIG.API_KEY}`
                },
                body: JSON.stringify(eventData)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            closeModal();
            dashboardInstance.showToast('Erfolg', 'Event erfolgreich aktualisiert!', 'success');
            setTimeout(() => dashboardInstance.refreshData(), 1000);

        } catch (error) {
            console.error('Error updating event:', error);
            dashboardInstance.showToast('Fehler', 'Event konnte nicht aktualisiert werden: ' + error.message, 'error');
        }
    } else {
        dashboardInstance.showToast('Fehler', 'Bitte füllen Sie alle Pflichtfelder aus.', 'error');
    }
}

async function deleteEvent(eventId) {
    if (confirm('Sind Sie sicher, dass Sie dieses Event löschen möchten?')) {
        try {
            const response = await fetch(`/api/v1/events/${eventId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${window.CHRONOS_CONFIG.API_KEY}`
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            closeModal();
            dashboardInstance.showToast('Erfolg', 'Event erfolgreich gelöscht!', 'success');
            setTimeout(() => dashboardInstance.refreshData(), 1000);

        } catch (error) {
            console.error('Error deleting event:', error);
            dashboardInstance.showToast('Fehler', 'Event konnte nicht gelöscht werden: ' + error.message, 'error');
        }
    }
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