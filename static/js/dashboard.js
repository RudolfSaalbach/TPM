"""
Enhanced Dashboard JavaScript - Dynamic API Integration
Replaces all static data with real API calls
"""

// Configuration
const CHRONOS_CONFIG = {
    API_BASE: '/api/v1',
    SYNC_BASE: '/sync',
    UPDATE_INTERVAL: 30000, // 30 seconds
    CHART_COLORS: {
        primary: '#667eea',
        secondary: '#764ba2',
        success: '#28a745',
        warning: '#ffc107',
        danger: '#dc3545',
        info: '#17a2b8'
    }
};

// API Helper Class
class ChronosAPI {
    static async get(url) {
        try {
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'Authorization': `Bearer ${this.getApiKey()}`
                }
            });
            
            if (!response.ok) {
                throw new Error(`API Error: ${response.status} ${response.statusText}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('API GET Error:', error);
            ChronosToast.error('API Error', `Failed to fetch data: ${error.message}`);
            throw error;
        }
    }
    
    static async post(url, data = {}) {
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Authorization': `Bearer ${this.getApiKey()}`
                },
                body: JSON.stringify(data)
            });
            
            if (!response.ok) {
                throw new Error(`API Error: ${response.status} ${response.statusText}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('API POST Error:', error);
            ChronosToast.error('API Error', `Failed to submit data: ${error.message}`);
            throw error;
        }
    }
    
    static getApiKey() {
        return 'development-key-change-in-production';
    }
}

// Toast Notification System
class ChronosToast {
    static show(title, message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <div class="toast-header">
                <strong>${title}</strong>
                <button type="button" class="close" onclick="this.parentElement.parentElement.remove()">×</button>
            </div>
            <div class="toast-body">${message}</div>
        `;
        
        const container = document.getElementById('toastContainer') || document.body;
        container.appendChild(toast);
        
        setTimeout(() => {
            if (toast.parentElement) {
                toast.remove();
            }
        }, 5000);
    }
    
    static success(title, message) { this.show(title, message, 'success'); }
    static error(title, message) { this.show(title, message, 'danger'); }
    static warning(title, message) { this.show(title, message, 'warning'); }
    static info(title, message) { this.show(title, message, 'info'); }
}

// Dashboard Manager
class ChronosDashboard {
    constructor() {
        this.data = { metrics: null, events: null, sync_status: null };
        this.isLoading = false;
    }
    
    async initialize() {
        console.log('🚀 Initializing Chronos Dashboard...');
        
        try {
            await this.loadAllData();
            this.setupAutoRefresh();
            this.setupEventListeners();
            console.log('✅ Dashboard initialized successfully');
        } catch (error) {
            console.error('❌ Dashboard initialization failed:', error);
            ChronosToast.error('Initialization Error', 'Failed to load dashboard data');
        }
    }
    
    async loadAllData() {
        if (this.isLoading) return;
        
        this.isLoading = true;
        this.showLoadingState();
        
        try {
            const [metricsResponse, eventsResponse, syncResponse] = await Promise.allSettled([
                this.loadProductivityMetrics(),
                this.loadRecentEvents(),
                this.loadSyncStatus()
            ]);
            
            if (metricsResponse.status === 'fulfilled') {
                this.data.metrics = metricsResponse.value;
                this.updateMetricsDisplay(this.data.metrics);
            }
            
            if (eventsResponse.status === 'fulfilled') {
                this.data.events = eventsResponse.value;
                this.updateEventsDisplay(this.data.events);
            }
            
            if (syncResponse.status === 'fulfilled') {
                this.data.sync_status = syncResponse.value;
                this.updateSyncStatusDisplay(this.data.sync_status);
            }
            
            this.hideLoadingState();
            
        } catch (error) {
            console.error('Error loading dashboard data:', error);
            this.hideLoadingState();
            throw error;
        } finally {
            this.isLoading = false;
        }
    }
    
    async loadProductivityMetrics() {
        try {
            const response = await ChronosAPI.get(`${CHRONOS_CONFIG.API_BASE}/analytics/productivity?days_back=30`);
            return response.metrics || {};
        } catch (error) {
            console.error('Failed to load productivity metrics:', error);
            return this.getFallbackMetrics();
        }
    }
    
    async loadRecentEvents() {
        try {
            const response = await ChronosAPI.get(`${CHRONOS_CONFIG.API_BASE}/events?limit=10`);
            return response.events || [];
        } catch (error) {
            console.error('Failed to load recent events:', error);
            return [];
        }
    }
    
    async loadSyncStatus() {
        try {
            const response = await ChronosAPI.get(`${CHRONOS_CONFIG.SYNC_BASE}/status`);
            return response.sync_status || {};
        } catch (error) {
            console.error('Failed to load sync status:', error);
            return this.getFallbackSyncStatus();
        }
    }
    
    updateMetricsDisplay(metrics) {
        this.updateElement('totalEvents', metrics.total_events || 0);
        this.updateElement('completionRate', `${((metrics.completion_rate || 0) * 100).toFixed(1)}%`);
        this.updateElement('avgProductivity', (metrics.average_productivity || 0).toFixed(1));
        this.updateElement('totalHours', (metrics.total_hours || 0).toFixed(1));
        this.updateElement('eventsPerDay', (metrics.events_per_day || 0).toFixed(1));
        
        this.updateProgressBar('completionProgress', (metrics.completion_rate || 0) * 100);
        this.updateProgressBar('productivityProgress', ((metrics.average_productivity || 0) / 5) * 100);
        
        console.log('📊 Metrics display updated');
    }
    
    updateEventsDisplay(events) {
        const eventsContainer = document.getElementById('recentEventsContainer');
        if (!eventsContainer) return;
        
        if (!events || events.length === 0) {
            eventsContainer.innerHTML = '<p class="text-muted">No recent events found.</p>';
            return;
        }
        
        eventsContainer.innerHTML = events.map(event => `
            <div class="event-item">
                <div class="event-header">
                    <h5>${event.title || 'Untitled Event'}</h5>
                    <span class="badge badge-${this.getPriorityColor(event.priority)}">${event.priority}</span>
                </div>
                <div class="event-details">
                    <p><i class="icon-calendar"></i> ${this.formatDateTime(event.start_time)}</p>
                    <p class="event-description">${event.description || 'No description available'}</p>
                </div>
                <div class="event-status">
                    <span class="status-badge status-${event.status.toLowerCase()}">${event.status}</span>
                </div>
            </div>
        `).join('');
        
        console.log('📅 Events display updated');
    }
    
    updateSyncStatusDisplay(syncStatus) {
        this.updateElement('syncTotalEvents', syncStatus.total_events || 0);
        this.updateElement('syncEarliestDate', this.formatDate(syncStatus.earliest_event));
        this.updateElement('syncLatestDate', this.formatDate(syncStatus.latest_event));
        
        if (syncStatus.quota_status) {
            const quota = syncStatus.quota_status;
            this.updateElement('quotaUsed', quota.daily_requests || 0);
            this.updateElement('quotaRemaining', quota.daily_remaining || 0);
            this.updateProgressBar('quotaProgress', ((quota.daily_requests || 0) / (quota.daily_limit || 1)) * 100);
        }
        
        console.log('🔄 Sync status display updated');
    }
    
    updateElement(id, content) {
        const element = document.getElementById(id);
        if (element) element.textContent = content;
    }
    
    updateProgressBar(id, percentage) {
        const progressBar = document.getElementById(id);
        if (progressBar) {
            progressBar.style.width = `${Math.min(percentage, 100)}%`;
            progressBar.setAttribute('aria-valuenow', percentage);
        }
    }
    
    showLoadingState() {
        const loadingElements = document.querySelectorAll('.loading-placeholder');
        loadingElements.forEach(el => el.classList.add('loading'));
    }
    
    hideLoadingState() {
        const loadingElements = document.querySelectorAll('.loading-placeholder');
        loadingElements.forEach(el => el.classList.remove('loading'));
    }
    
    setupAutoRefresh() {
        setInterval(async () => {
            if (!document.hidden && !this.isLoading) {
                console.log('🔄 Auto-refreshing dashboard data...');
                await this.loadAllData();
            }
        }, CHRONOS_CONFIG.UPDATE_INTERVAL);
    }
    
    setupEventListeners() {
        const refreshBtn = document.getElementById('refreshDashboard');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', async () => {
                await this.loadAllData();
                ChronosToast.success('Refresh Complete', 'Dashboard data updated');
            });
        }
        
        this.setupSyncButtons();
    }
    
    setupSyncButtons() {
        const completeSyncBtn = document.getElementById('triggerCompleteSync');
        if (completeSyncBtn) {
            completeSyncBtn.addEventListener('click', async () => {
                try {
                    const response = await ChronosAPI.post(`${CHRONOS_CONFIG.SYNC_BASE}/calendar/complete`);
                    ChronosToast.success('Sync Started', response.message);
                } catch (error) {
                    ChronosToast.error('Sync Failed', 'Could not start complete sync');
                }
            });
        }
        
        const incrementalSyncBtn = document.getElementById('triggerIncrementalSync');
        if (incrementalSyncBtn) {
            incrementalSyncBtn.addEventListener('click', async () => {
                try {
                    const response = await ChronosAPI.post(`${CHRONOS_CONFIG.SYNC_BASE}/calendar/incremental`);
                    ChronosToast.success('Sync Complete', response.message);
                } catch (error) {
                    ChronosToast.error('Sync Failed', 'Could not perform incremental sync');
                }
            });
        }
    }
    
    getPriorityColor(priority) {
        const colors = {
            'URGENT': 'danger',
            'HIGH': 'warning', 
            'MEDIUM': 'info',
            'LOW': 'secondary'
        };
        return colors[priority] || 'secondary';
    }
    
    formatDateTime(dateString) {
        if (!dateString) return 'No date';
        try {
            return new Date(dateString).toLocaleString();
        } catch {
            return 'Invalid date';
        }
    }
    
    formatDate(dateString) {
        if (!dateString) return 'N/A';
        try {
            return new Date(dateString).toLocaleDateString();
        } catch {
            return 'Invalid';
        }
    }
    
    getFallbackMetrics() {
        return {
            total_events: 0,
            completion_rate: 0,
            average_productivity: 0,
            total_hours: 0,
            events_per_day: 0
        };
    }
    
    getFallbackSyncStatus() {
        return {
            total_events: 0,
            earliest_event: null,
            latest_event: null,
            quota_status: {
                daily_requests: 0,
                daily_remaining: 100000,
                daily_limit: 100000
            }
        };
    }
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    const dashboard = new ChronosDashboard();
    dashboard.initialize();
});
