/**
 * FilterPanel Component - Sidebar filter controls
 * Refactored from monolithic chronos_gui_client.html
 */
class FilterPanelComponent extends ChronosComponent {

    get defaultOptions() {
        return {
            ...super.defaultOptions,
            className: 'filter-panel-component',
            persistFilters: true,
            storageKey: 'chronos_filters'
        };
    }

    get defaultState() {
        return {
            ...super.defaultState,
            filters: {
                range: '7',
                direction: 'future',
                calendar: 'primary',
                searchQuery: ''
            },
            availableCalendars: ['primary'],
            rangeOptions: [
                { value: '7', label: '7 Tage' },
                { value: '14', label: '14 Tage' },
                { value: '30', label: '30 Tage' },
                { value: '60', label: '60 Tage' },
                { value: '360', label: '360 Tage' },
                { value: '-1', label: 'Alle' }
            ],
            directionOptions: [
                { value: 'past', label: 'Vergangenheit' },
                { value: 'future', label: 'Zukunft' },
                { value: 'all', label: 'Alles' }
            ]
        };
    }

    init() {
        // Load saved filters before initialization
        if (this.options.persistFilters) {
            this.loadSavedFilters();
        }

        super.init();

        // Apply initial filters
        this.applyFilters();
    }

    setupDOMReferences() {
        super.setupDOMReferences();

        this.refs = {
            ...this.refs,
            rangeSelect: this.element.querySelector('[data-ref="range"]'),
            directionRadios: this.element.querySelectorAll('[name="direction"]'),
            calendarSelect: this.element.querySelector('[data-ref="calendar"]'),
            searchInput: this.element.querySelector('[data-ref="search"]'),
            clearButton: this.element.querySelector('[data-ref="clear"]'),
            newEventButton: this.element.querySelector('[data-ref="new-event"]'),
            templatesButton: this.element.querySelector('[data-ref="templates"]')
        };
    }

    setupEventListeners() {
        super.setupEventListeners();

        // Range selector
        if (this.refs.rangeSelect) {
            this.addEventListener(this.refs.rangeSelect, 'change', this.handleRangeChange.bind(this));
        }

        // Direction radio buttons
        this.refs.directionRadios.forEach(radio => {
            this.addEventListener(radio, 'change', this.handleDirectionChange.bind(this));
        });

        // Calendar selector
        if (this.refs.calendarSelect) {
            this.addEventListener(this.refs.calendarSelect, 'change', this.handleCalendarChange.bind(this));
        }

        // Search input
        if (this.refs.searchInput) {
            this.addEventListener(this.refs.searchInput, 'input',
                this.debounce(this.handleSearchInput.bind(this), 300));
        }

        // Clear button
        if (this.refs.clearButton) {
            this.addEventListener(this.refs.clearButton, 'click', this.clearFilters.bind(this));
        }

        // Action buttons
        if (this.refs.newEventButton) {
            this.addEventListener(this.refs.newEventButton, 'click', this.handleNewEvent.bind(this));
        }

        if (this.refs.templatesButton) {
            this.addEventListener(this.refs.templatesButton, 'click', this.handleTemplates.bind(this));
        }

        // Global events
        this.subscribe('calendars:updated', this.updateCalendarOptions.bind(this));
        this.subscribe('filters:reset', this.resetFilters.bind(this));
        this.subscribe('filters:apply', this.handleExternalFilters.bind(this));

        // Keyboard shortcuts
        this.addEventListener(document, 'keydown', this.handleKeyboardShortcuts.bind(this));
    }

    /**
     * Render the filter panel
     */
    render() {
        super.render();

        this.updateRangeSelector();
        this.updateDirectionRadios();
        this.updateCalendarSelector();
        this.updateSearchInput();
    }

    /**
     * Update range selector
     */
    updateRangeSelector() {
        if (!this.refs.rangeSelect) return;

        // Clear and populate options
        this.refs.rangeSelect.innerHTML = '';
        this.state.rangeOptions.forEach(option => {
            const optionElement = document.createElement('option');
            optionElement.value = option.value;
            optionElement.textContent = option.label;
            optionElement.selected = option.value === this.state.filters.range;
            this.refs.rangeSelect.appendChild(optionElement);
        });
    }

    /**
     * Update direction radio buttons
     */
    updateDirectionRadios() {
        this.refs.directionRadios.forEach(radio => {
            radio.checked = radio.value === this.state.filters.direction;
        });
    }

    /**
     * Update calendar selector
     */
    updateCalendarSelector() {
        if (!this.refs.calendarSelect) return;

        // Clear and populate options
        this.refs.calendarSelect.innerHTML = '';
        this.state.availableCalendars.forEach(calendar => {
            const optionElement = document.createElement('option');
            optionElement.value = calendar;
            optionElement.textContent = this.formatCalendarName(calendar);
            optionElement.selected = calendar === this.state.filters.calendar;
            this.refs.calendarSelect.appendChild(optionElement);
        });
    }

    /**
     * Update search input
     */
    updateSearchInput() {
        if (this.refs.searchInput) {
            this.refs.searchInput.value = this.state.filters.searchQuery;
        }
    }

    /**
     * Handle range change
     */
    handleRangeChange(event) {
        const range = event.target.value;
        this.updateFilter('range', range);
    }

    /**
     * Handle direction change
     */
    handleDirectionChange(event) {
        const direction = event.target.value;
        this.updateFilter('direction', direction);
    }

    /**
     * Handle calendar change
     */
    handleCalendarChange(event) {
        const calendar = event.target.value;
        this.updateFilter('calendar', calendar);
    }

    /**
     * Handle search input
     */
    handleSearchInput(event) {
        const searchQuery = event.target.value;
        this.updateFilter('searchQuery', searchQuery);
    }

    /**
     * Update a single filter
     */
    updateFilter(key, value) {
        const newFilters = { ...this.state.filters, [key]: value };
        this.setState({ filters: newFilters });

        // Save filters
        if (this.options.persistFilters) {
            this.saveFilters();
        }

        // Apply filters
        this.applyFilters();

        this.emit('filters:changed', { [key]: value }, newFilters);
    }

    /**
     * Apply current filters
     */
    applyFilters() {
        const filters = { ...this.state.filters };

        // Add computed anchor date
        filters.anchor = this.getTodayLocalDate();

        this.emit('filters:apply', filters);
    }

    /**
     * Clear all filters
     */
    clearFilters() {
        const defaultFilters = {
            range: '7',
            direction: 'future',
            calendar: 'primary',
            searchQuery: ''
        };

        this.setState({ filters: defaultFilters });

        // Update UI
        this.render();

        // Save and apply
        if (this.options.persistFilters) {
            this.saveFilters();
        }

        this.applyFilters();
        this.emit('filters:cleared', defaultFilters);
    }

    /**
     * Reset filters to saved state
     */
    resetFilters() {
        if (this.options.persistFilters) {
            this.loadSavedFilters();
            this.render();
            this.applyFilters();
        } else {
            this.clearFilters();
        }
    }

    /**
     * Handle external filter updates
     */
    handleExternalFilters(filters) {
        const newFilters = { ...this.state.filters, ...filters };
        this.setState({ filters: newFilters });

        if (this.options.persistFilters) {
            this.saveFilters();
        }

        this.render();
    }

    /**
     * Handle new event button
     */
    handleNewEvent() {
        this.emit('events:newEvent');
    }

    /**
     * Handle templates button
     */
    handleTemplates() {
        this.emit('templates:open');
    }

    /**
     * Handle keyboard shortcuts
     */
    handleKeyboardShortcuts(event) {
        if (event.ctrlKey || event.metaKey) {
            switch (event.key.toLowerCase()) {
                case 't':
                    event.preventDefault();
                    this.handleTemplates();
                    break;

                case 'n':
                    event.preventDefault();
                    this.handleNewEvent();
                    break;

                case 'f':
                    event.preventDefault();
                    if (this.refs.searchInput) {
                        this.refs.searchInput.focus();
                    }
                    break;

                case 'r':
                    if (event.shiftKey) {
                        event.preventDefault();
                        this.resetFilters();
                    }
                    break;
            }
        }

        // Quick filter shortcuts
        if (event.altKey) {
            switch (event.key) {
                case '1':
                    event.preventDefault();
                    this.updateFilter('range', '7');
                    break;
                case '2':
                    event.preventDefault();
                    this.updateFilter('range', '30');
                    break;
                case '3':
                    event.preventDefault();
                    this.updateFilter('range', '-1');
                    break;
                case 'p':
                    event.preventDefault();
                    this.updateFilter('direction', 'past');
                    break;
                case 'f':
                    event.preventDefault();
                    this.updateFilter('direction', 'future');
                    break;
                case 'a':
                    event.preventDefault();
                    this.updateFilter('direction', 'all');
                    break;
            }
        }
    }

    /**
     * Update calendar options
     */
    updateCalendarOptions(calendars) {
        this.setState({ availableCalendars: calendars });
        this.updateCalendarSelector();
    }

    /**
     * Format calendar name for display
     */
    formatCalendarName(calendar) {
        const nameMap = {
            'primary': 'Primary Calendar',
            'work': 'Work Calendar',
            'personal': 'Personal Calendar',
            'google_calendar': 'Google Calendar',
            'outlook_calendar': 'Outlook Calendar'
        };

        return nameMap[calendar] || calendar.charAt(0).toUpperCase() + calendar.slice(1);
    }

    /**
     * Save filters to localStorage
     */
    saveFilters() {
        try {
            const filtersToSave = {
                ...this.state.filters,
                savedAt: new Date().toISOString()
            };
            localStorage.setItem(this.options.storageKey, JSON.stringify(filtersToSave));
            this.debug('Filters saved to localStorage');
        } catch (error) {
            this.debug('Failed to save filters:', error);
        }
    }

    /**
     * Load filters from localStorage
     */
    loadSavedFilters() {
        try {
            const saved = localStorage.getItem(this.options.storageKey);
            if (saved) {
                const filters = JSON.parse(saved);

                // Remove savedAt timestamp
                delete filters.savedAt;

                // Merge with current filters
                this.setState({
                    filters: { ...this.state.filters, ...filters }
                });

                this.debug('Filters loaded from localStorage');
            }
        } catch (error) {
            this.debug('Failed to load saved filters:', error);
        }
    }

    /**
     * Get today's date in local format
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
     * Public API: Get current filters
     */
    getFilters() {
        return { ...this.state.filters };
    }

    /**
     * Public API: Set filters
     */
    setFilters(filters) {
        const newFilters = { ...this.state.filters, ...filters };
        this.setState({ filters: newFilters });

        if (this.options.persistFilters) {
            this.saveFilters();
        }

        this.render();
        this.applyFilters();
    }

    /**
     * Public API: Get filter value
     */
    getFilter(key) {
        return this.state.filters[key];
    }

    /**
     * Public API: Set single filter value
     */
    setFilter(key, value) {
        this.updateFilter(key, value);
    }

    /**
     * Public API: Add calendar option
     */
    addCalendar(calendar) {
        if (!this.state.availableCalendars.includes(calendar)) {
            const newCalendars = [...this.state.availableCalendars, calendar];
            this.setState({ availableCalendars: newCalendars });
            this.updateCalendarSelector();
        }
    }

    /**
     * Public API: Remove calendar option
     */
    removeCalendar(calendar) {
        const newCalendars = this.state.availableCalendars.filter(c => c !== calendar);
        this.setState({ availableCalendars: newCalendars });

        // If removed calendar was selected, switch to primary
        if (this.state.filters.calendar === calendar) {
            this.updateFilter('calendar', 'primary');
        }

        this.updateCalendarSelector();
    }

    /**
     * Public API: Focus search input
     */
    focusSearch() {
        if (this.refs.searchInput) {
            this.refs.searchInput.focus();
        }
    }

    /**
     * Public API: Get available shortcuts help
     */
    getShortcutsHelp() {
        return {
            'Ctrl+T': 'Open templates',
            'Ctrl+N': 'New event',
            'Ctrl+F': 'Focus search',
            'Ctrl+Shift+R': 'Reset filters',
            'Alt+1': '7 days range',
            'Alt+2': '30 days range',
            'Alt+3': 'All events',
            'Alt+P': 'Past events',
            'Alt+F': 'Future events',
            'Alt+A': 'All events'
        };
    }
}

// Register component globally
window.FilterPanelComponent = FilterPanelComponent;

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = FilterPanelComponent;
}