/**
 * EventList Component - Displays and manages event lists
 * Refactored from monolithic chronos_gui_client.html
 */
class EventListComponent extends ChronosComponent {

    get defaultOptions() {
        return {
            ...super.defaultOptions,
            className: 'event-list-component',
            apiEndpoint: '/api/v1/events',
            pageSize: 100,
            enableSearch: true,
            enableFilters: true,
            autoRefresh: false,
            refreshInterval: 300000 // 5 minutes
        };
    }

    get defaultState() {
        return {
            ...super.defaultState,
            events: [],
            filteredEvents: [],
            searchQuery: '',
            filters: {
                range: '7',
                direction: 'future',
                calendar: 'primary',
                anchor: this.getTodayLocalDate()
            },
            pagination: {
                page: 1,
                pageSize: 100,
                total: 0
            },
            selectedEvent: null,
            lastUpdate: null
        };
    }

    setupDOMReferences() {
        super.setupDOMReferences();

        // Additional refs specific to EventList
        this.refs = {
            ...this.refs,
            list: this.element.querySelector('[data-ref="list"]') || this.element.querySelector('.list'),
            searchInput: this.element.querySelector('[data-ref="search"]'),
            rangeSelect: this.element.querySelector('[data-ref="range"]'),
            directionRadios: this.element.querySelectorAll('[name="direction"]'),
            statusElement: this.element.querySelector('[data-ref="status"]'),
            countElement: this.element.querySelector('[data-ref="count"]')
        };
    }

    setupEventListeners() {
        super.setupEventListeners();

        // Search input
        if (this.refs.searchInput) {
            this.addEventListener(this.refs.searchInput, 'input',
                this.debounce(this.handleSearchInput.bind(this), 300));
        }

        // Range selector
        if (this.refs.rangeSelect) {
            this.addEventListener(this.refs.rangeSelect, 'change', this.handleRangeChange.bind(this));
        }

        // Direction radio buttons
        this.refs.directionRadios.forEach(radio => {
            this.addEventListener(radio, 'change', this.handleDirectionChange.bind(this));
        });

        // Subscribe to global events
        this.subscribe('events:refresh', this.loadEvents.bind(this));
        this.subscribe('events:filter', this.handleExternalFilter.bind(this));
        this.subscribe('calendar:synced', this.loadEvents.bind(this));

        // Auto-refresh
        if (this.options.autoRefresh) {
            this.startAutoRefresh();
        }
    }

    /**
     * Load events from API
     */
    async loadEvents() {
        if (this.isDestroyed) return;

        try {
            this.showLoading('Loading events...');
            this.updateStatus('Loading...');

            const params = this.buildAPIParams();
            const response = await this.fetchEvents(params);

            this.setState({
                events: response.items || [],
                pagination: {
                    ...this.state.pagination,
                    total: response.total || 0
                },
                lastUpdate: new Date()
            });

            this.applyFilters();
            this.updateStatus(`${this.state.events.length} events loaded`);
            this.updateCount(this.state.filteredEvents.length);

            this.emit('events:loaded', this.state.events);

        } catch (error) {
            this.handleLoadError(error);
        } finally {
            this.hideLoading();
        }
    }

    /**
     * Build API parameters from current state
     */
    buildAPIParams() {
        return {
            calendar: this.state.filters.calendar,
            anchor: this.state.filters.anchor,
            range: this.state.filters.range,
            direction: this.state.filters.range === '-1' ? 'all' : this.state.filters.direction,
            q: this.state.searchQuery,
            page: this.state.pagination.page,
            page_size: this.state.pagination.pageSize
        };
    }

    /**
     * Fetch events from API
     */
    async fetchEvents(params) {
        const url = new URL(this.options.apiEndpoint, window.location.origin);

        // Add parameters
        Object.entries(params).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') {
                url.searchParams.append(key, value);
            }
        });

        const response = await fetch(url.toString(), {
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                ...(window.ChronosAPI?.getAuthHeaders?.() || {})
            }
        });

        if (!response.ok) {
            throw new Error(`API Error ${response.status}: ${await response.text()}`);
        }

        return await response.json();
    }

    /**
     * Apply search and filters to events
     */
    applyFilters() {
        let filtered = [...this.state.events];

        // Apply search
        if (this.state.searchQuery) {
            const query = this.state.searchQuery.toLowerCase();
            filtered = filtered.filter(event =>
                (event.title || '').toLowerCase().includes(query) ||
                (event.description || '').toLowerCase().includes(query)
            );
        }

        this.setState({ filteredEvents: filtered }, false);
        this.render();
    }

    /**
     * Handle search input changes
     */
    handleSearchInput(event) {
        const query = event.target.value;
        this.setState({ searchQuery: query });
        this.applyFilters();
        this.emit('events:searchChanged', query);
    }

    /**
     * Handle range selector changes
     */
    handleRangeChange(event) {
        const range = event.target.value;
        this.setState({
            filters: { ...this.state.filters, range }
        });
        this.loadEvents();
        this.emit('events:rangeChanged', range);
    }

    /**
     * Handle direction radio changes
     */
    handleDirectionChange(event) {
        const direction = event.target.value;
        this.setState({
            filters: { ...this.state.filters, direction }
        });
        this.loadEvents();
        this.emit('events:directionChanged', direction);
    }

    /**
     * Handle external filter changes
     */
    handleExternalFilter(filters) {
        this.setState({
            filters: { ...this.state.filters, ...filters }
        });
        this.loadEvents();
    }

    /**
     * Render the event list
     */
    render() {
        if (!this.refs.list) return;

        super.render();

        const { filteredEvents, searchQuery } = this.state;

        this.refs.list.innerHTML = '';

        if (filteredEvents.length === 0) {
            this.renderEmptyState();
            return;
        }

        const fragment = document.createDocumentFragment();
        const searchTokens = this.getSearchTokens(searchQuery);

        filteredEvents.forEach(event => {
            const eventElement = this.createEventElement(event, searchTokens);
            fragment.appendChild(eventElement);
        });

        this.refs.list.appendChild(fragment);
        this.emit('events:rendered', filteredEvents);
    }

    /**
     * Create individual event element
     */
    createEventElement(event, searchTokens = []) {
        const card = document.createElement('div');
        card.className = 'event-card';
        card.setAttribute('data-event-id', event.id);

        const title = this.highlightText(event.title || '(ohne Titel)', searchTokens);
        const description = this.highlightText(event.description || '', searchTokens);

        const isAllDay = !!event.all_day;
        const timeDisplay = isAllDay
            ? this.formatDate(event.all_day_date)
            : `${this.formatDateTime(event.start_utc)} – ${this.formatDateTime(event.end_utc)}`;

        card.innerHTML = `
            <div class="event-header">
                <div class="event-info">
                    <div class="event-title">${title}</div>
                    <div class="event-description">${description}</div>
                </div>
                <div class="event-meta">
                    <span class="event-type-badge ${isAllDay ? 'all-day' : 'timed'}">
                        ${isAllDay ? 'Ganztägig' : 'Zeitgebunden'}
                    </span>
                </div>
            </div>
            <div class="event-time">${timeDisplay}</div>
        `;

        // Add click handler
        this.addEventListener(card, 'click', () => this.selectEvent(event));

        // Add keyboard navigation
        card.tabIndex = 0;
        this.addEventListener(card, 'keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                this.selectEvent(event);
            }
        });

        return card;
    }

    /**
     * Render empty state
     */
    renderEmptyState() {
        this.refs.list.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📅</div>
                <div class="empty-title">No events found</div>
                <div class="empty-subtitle">
                    ${this.state.searchQuery
                        ? 'Try adjusting your search criteria'
                        : 'No events in the selected time range'
                    }
                </div>
            </div>
        `;
    }

    /**
     * Select an event
     */
    selectEvent(event) {
        this.setState({ selectedEvent: event });

        // Update visual selection
        this.refs.list.querySelectorAll('.event-card').forEach(card => {
            card.classList.remove('selected');
        });

        const selectedCard = this.refs.list.querySelector(`[data-event-id="${event.id}"]`);
        if (selectedCard) {
            selectedCard.classList.add('selected');
        }

        this.emit('events:eventSelected', event);
    }

    /**
     * Update status message
     */
    updateStatus(message) {
        if (this.refs.statusElement) {
            this.refs.statusElement.textContent = message;
            this.refs.statusElement.classList.remove('error');
        }
    }

    /**
     * Update count display
     */
    updateCount(count) {
        if (this.refs.countElement) {
            this.refs.countElement.textContent = String(count);
        }
    }

    /**
     * Handle load errors
     */
    handleLoadError(error) {
        this.showError(error);
        this.updateStatus(error.message || 'Error loading events');

        if (this.refs.statusElement) {
            this.refs.statusElement.classList.add('error');
        }

        // Show retry button
        this.refs.list.innerHTML = `
            <div class="error-state">
                <div class="error-icon">⚠️</div>
                <div class="error-title">Failed to load events</div>
                <div class="error-message">${this.escapeHtml(error.message || 'Unknown error')}</div>
                <button class="retry-button" data-ref="retryButton">
                    Try Again
                </button>
            </div>
        `;

        const retryButton = this.refs.list.querySelector('[data-ref="retryButton"]');
        if (retryButton) {
            this.addEventListener(retryButton, 'click', () => this.loadEvents());
        }

        this.emit('events:loadError', error);
    }

    /**
     * Start auto-refresh timer
     */
    startAutoRefresh() {
        if (this.autoRefreshTimer) {
            clearInterval(this.autoRefreshTimer);
        }

        this.autoRefreshTimer = setInterval(() => {
            if (document.visibilityState === 'visible') {
                this.loadEvents();
            }
        }, this.options.refreshInterval);
    }

    /**
     * Stop auto-refresh timer
     */
    stopAutoRefresh() {
        if (this.autoRefreshTimer) {
            clearInterval(this.autoRefreshTimer);
            this.autoRefreshTimer = null;
        }
    }

    /**
     * Utility: Get search tokens
     */
    getSearchTokens(query) {
        return (query || '').trim().toLowerCase().split(/\s+/).filter(Boolean);
    }

    /**
     * Utility: Highlight text
     */
    highlightText(text, tokens) {
        if (!tokens || tokens.length === 0) {
            return this.escapeHtml(text);
        }

        let highlighted = this.escapeHtml(text);
        tokens.forEach(token => {
            const regex = new RegExp(`(${token.replace(/[-/\\^$*+?.()|[\]{}]/g, '\\$&')})`, 'gi');
            highlighted = highlighted.replace(regex, '<mark>$1</mark>');
        });

        return highlighted;
    }

    /**
     * Utility: Escape HTML
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Utility: Format date/time
     */
    formatDateTime(isoString) {
        if (!isoString) return '';
        try {
            const date = new Date(isoString);
            return date.toLocaleString('de-DE', {
                timeZone: 'Europe/Berlin',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch {
            return isoString;
        }
    }

    /**
     * Utility: Format date
     */
    formatDate(dateString) {
        return dateString || '';
    }

    /**
     * Utility: Get today's date in local format
     */
    getTodayLocalDate() {
        const d = new Date();
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    /**
     * Utility: Debounce function
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
     * Cleanup on destroy
     */
    destroy() {
        this.stopAutoRefresh();
        super.destroy();
    }

    /**
     * Public API: Refresh events
     */
    refresh() {
        return this.loadEvents();
    }

    /**
     * Public API: Set search query
     */
    setSearchQuery(query) {
        this.setState({ searchQuery: query });
        this.applyFilters();

        if (this.refs.searchInput) {
            this.refs.searchInput.value = query;
        }
    }

    /**
     * Public API: Set filters
     */
    setFilters(filters) {
        this.setState({
            filters: { ...this.state.filters, ...filters }
        });
        this.loadEvents();
    }

    /**
     * Public API: Get selected event
     */
    getSelectedEvent() {
        return this.state.selectedEvent;
    }

    /**
     * Public API: Get all events
     */
    getEvents() {
        return [...this.state.events];
    }

    /**
     * Public API: Get filtered events
     */
    getFilteredEvents() {
        return [...this.state.filteredEvents];
    }
}

// Register component globally
window.EventListComponent = EventListComponent;

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = EventListComponent;
}