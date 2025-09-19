/**
 * TemplateModal Component - Modal for template selection and management
 * Refactored from monolithic chronos_gui_client.html
 */
class TemplateModalComponent extends ChronosComponent {

    get defaultOptions() {
        return {
            ...super.defaultOptions,
            className: 'template-modal-component',
            apiEndpoint: '/api/v1/templates',
            autoFocus: true,
            closeOnBackdrop: true,
            closeOnEscape: true
        };
    }

    get defaultState() {
        return {
            ...super.defaultState,
            isOpen: false,
            templates: [],
            filteredTemplates: [],
            searchQuery: '',
            selectedTemplate: null,
            focusedIndex: -1
        };
    }

    setupDOMReferences() {
        super.setupDOMReferences();

        this.refs = {
            ...this.refs,
            modal: this.element.querySelector('[data-ref="modal"]') || this.element,
            backdrop: this.element.querySelector('[data-ref="backdrop"]'),
            searchInput: this.element.querySelector('[data-ref="search"]'),
            templatesList: this.element.querySelector('[data-ref="templates-list"]'),
            detailsPanel: this.element.querySelector('[data-ref="details"]'),
            closeButton: this.element.querySelector('[data-ref="close"]'),
            applyButton: this.element.querySelector('[data-ref="apply"]'),
            deleteButton: this.element.querySelector('[data-ref="delete"]')
        };
    }

    setupEventListeners() {
        super.setupEventListeners();

        // Search input
        if (this.refs.searchInput) {
            this.addEventListener(this.refs.searchInput, 'input',
                this.debounce(this.handleSearchInput.bind(this), 300));
        }

        // Close button
        if (this.refs.closeButton) {
            this.addEventListener(this.refs.closeButton, 'click', this.close.bind(this));
        }

        // Apply button
        if (this.refs.applyButton) {
            this.addEventListener(this.refs.applyButton, 'click', this.handleApplyTemplate.bind(this));
        }

        // Delete button
        if (this.refs.deleteButton) {
            this.addEventListener(this.refs.deleteButton, 'click', this.handleDeleteTemplate.bind(this));
        }

        // Backdrop click
        if (this.refs.backdrop && this.options.closeOnBackdrop) {
            this.addEventListener(this.refs.backdrop, 'click', (e) => {
                if (e.target === this.refs.backdrop) {
                    this.close();
                }
            });
        }

        // Keyboard events
        if (this.options.closeOnEscape) {
            this.addEventListener(document, 'keydown', this.handleKeydown.bind(this));
        }

        // Global events
        this.subscribe('templates:open', this.open.bind(this));
        this.subscribe('templates:close', this.close.bind(this));
        this.subscribe('templates:refresh', this.loadTemplates.bind(this));
    }

    /**
     * Open the modal
     */
    async open() {
        if (this.state.isOpen) return;

        this.setState({ isOpen: true });

        // Show modal
        this.refs.modal.showModal?.() || this.showModal();

        // Load templates
        await this.loadTemplates();

        // Focus management
        if (this.options.autoFocus && this.refs.searchInput) {
            this.refs.searchInput.focus();
        }

        // Prevent body scroll
        document.body.style.overflow = 'hidden';

        this.emit('templates:opened');
    }

    /**
     * Close the modal
     */
    close() {
        if (!this.state.isOpen) return;

        this.setState({
            isOpen: false,
            selectedTemplate: null,
            searchQuery: '',
            focusedIndex: -1
        });

        // Hide modal
        this.refs.modal.close?.() || this.hideModal();

        // Restore body scroll
        document.body.style.overflow = '';

        // Clear search
        if (this.refs.searchInput) {
            this.refs.searchInput.value = '';
        }

        this.emit('templates:closed');
    }

    /**
     * Show modal (fallback for browsers without dialog support)
     */
    showModal() {
        this.element.style.display = 'flex';
        this.element.setAttribute('aria-modal', 'true');
        this.element.setAttribute('aria-hidden', 'false');
    }

    /**
     * Hide modal (fallback for browsers without dialog support)
     */
    hideModal() {
        this.element.style.display = 'none';
        this.element.setAttribute('aria-modal', 'false');
        this.element.setAttribute('aria-hidden', 'true');
    }

    /**
     * Load templates from API
     */
    async loadTemplates() {
        try {
            this.showLoading('Loading templates...');

            const response = await this.fetchTemplates({
                q: this.state.searchQuery,
                page: 1,
                page_size: 100
            });

            this.setState({
                templates: response.items || [],
                filteredTemplates: response.items || []
            });

            this.renderTemplates();

        } catch (error) {
            this.handleLoadError(error);
        } finally {
            this.hideLoading();
        }
    }

    /**
     * Fetch templates from API
     */
    async fetchTemplates(params) {
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
     * Handle search input
     */
    handleSearchInput(event) {
        const query = event.target.value;
        this.setState({ searchQuery: query, focusedIndex: -1 });
        this.filterTemplates(query);
    }

    /**
     * Filter templates by search query
     */
    filterTemplates(query) {
        if (!query.trim()) {
            this.setState({ filteredTemplates: [...this.state.templates] });
        } else {
            const lowercaseQuery = query.toLowerCase();
            const filtered = this.state.templates.filter(template =>
                (template.title || '').toLowerCase().includes(lowercaseQuery) ||
                (template.description || '').toLowerCase().includes(lowercaseQuery) ||
                (template.tags || []).some(tag => tag.toLowerCase().includes(lowercaseQuery))
            );
            this.setState({ filteredTemplates: filtered });
        }

        this.renderTemplates();
    }

    /**
     * Render templates list
     */
    renderTemplates() {
        if (!this.refs.templatesList) return;

        const { filteredTemplates, searchQuery } = this.state;
        this.refs.templatesList.innerHTML = '';

        if (filteredTemplates.length === 0) {
            this.renderEmptyTemplates();
            return;
        }

        const fragment = document.createDocumentFragment();
        const searchTokens = this.getSearchTokens(searchQuery);

        filteredTemplates.forEach((template, index) => {
            const templateElement = this.createTemplateElement(template, searchTokens, index);
            fragment.appendChild(templateElement);
        });

        this.refs.templatesList.appendChild(fragment);
    }

    /**
     * Create template element
     */
    createTemplateElement(template, searchTokens, index) {
        const element = document.createElement('button');
        element.type = 'button';
        element.className = 'template-item';
        element.setAttribute('data-template-id', template.id);
        element.setAttribute('data-index', index);

        const title = this.highlightText(template.title || 'Untitled', searchTokens);
        const description = this.highlightText(template.description || '', searchTokens);
        const tags = (template.tags || []).map(tag => this.escapeHtml(tag)).join(', ');

        element.innerHTML = `
            <div class="template-header">
                <div class="template-title">${title}</div>
                <div class="template-meta">
                    <span class="usage-count">${template.usage_count || 0}×</span>
                </div>
            </div>
            <div class="template-description">${description}</div>
            ${tags ? `<div class="template-tags">Tags: ${tags}</div>` : ''}
        `;

        // Click handler
        this.addEventListener(element, 'click', () => this.selectTemplate(template, index));

        // Keyboard navigation
        this.addEventListener(element, 'keydown', (e) => {
            this.handleTemplateKeydown(e, index);
        });

        return element;
    }

    /**
     * Render empty templates state
     */
    renderEmptyTemplates() {
        this.refs.templatesList.innerHTML = `
            <div class="empty-templates">
                <div class="empty-icon">📝</div>
                <div class="empty-title">No templates found</div>
                <div class="empty-subtitle">
                    ${this.state.searchQuery
                        ? 'Try adjusting your search criteria'
                        : 'No templates available'
                    }
                </div>
            </div>
        `;
    }

    /**
     * Select a template
     */
    selectTemplate(template, index) {
        this.setState({
            selectedTemplate: template,
            focusedIndex: index
        });

        // Update visual selection
        this.refs.templatesList.querySelectorAll('.template-item').forEach((item, i) => {
            item.classList.toggle('selected', i === index);
        });

        this.renderTemplateDetails(template);
        this.emit('templates:templateSelected', template);
    }

    /**
     * Render template details panel
     */
    renderTemplateDetails(template) {
        if (!this.refs.detailsPanel) return;

        const timeInfo = template.all_day
            ? 'All-day event'
            : `Default time: ${template.default_time || '—'} · Duration: ${template.duration_minutes || '—'} min`;

        this.refs.detailsPanel.innerHTML = `
            <div class="template-details">
                <div class="detail-title">${this.escapeHtml(template.title || 'Untitled')}</div>
                <div class="detail-description">${this.escapeHtml(template.description || '')}</div>
                <div class="detail-meta">${timeInfo}</div>
                <div class="detail-tags">
                    Tags: ${(template.tags || []).map(tag => this.escapeHtml(tag)).join(', ') || '—'}
                </div>

                <div class="detail-actions">
                    <button class="btn btn-primary" data-ref="apply">
                        Use Template
                    </button>
                    <span class="usage-info">Used ${template.usage_count || 0} times</span>
                </div>

                <div class="detail-danger-zone">
                    <button class="btn btn-danger btn-sm" data-ref="delete">
                        Delete Template
                    </button>
                    <small class="template-id">ID: ${template.id}</small>
                </div>
            </div>
        `;

        // Re-bind action buttons
        this.setupDetailsEventListeners();
    }

    /**
     * Setup event listeners for details panel
     */
    setupDetailsEventListeners() {
        const applyBtn = this.refs.detailsPanel.querySelector('[data-ref="apply"]');
        const deleteBtn = this.refs.detailsPanel.querySelector('[data-ref="delete"]');

        if (applyBtn) {
            this.addEventListener(applyBtn, 'click', this.handleApplyTemplate.bind(this));
        }

        if (deleteBtn) {
            this.addEventListener(deleteBtn, 'click', this.handleDeleteTemplate.bind(this));
        }
    }

    /**
     * Handle applying a template
     */
    async handleApplyTemplate() {
        if (!this.state.selectedTemplate) return;

        try {
            await this.applyTemplate(this.state.selectedTemplate.id);
            this.emit('templates:templateApplied', this.state.selectedTemplate);
            this.close();
        } catch (error) {
            this.showError(error);
            this.emit('templates:applyError', error);
        }
    }

    /**
     * Apply template via API
     */
    async applyTemplate(templateId) {
        const response = await fetch(`${this.options.apiEndpoint}/${templateId}/use`, {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                ...(window.ChronosAPI?.getAuthHeaders?.() || {})
            }
        });

        if (!response.ok) {
            throw new Error(`Failed to apply template: ${response.status}`);
        }

        return await response.json();
    }

    /**
     * Handle deleting a template
     */
    async handleDeleteTemplate() {
        if (!this.state.selectedTemplate) return;

        const template = this.state.selectedTemplate;
        const confirmMessage = `Are you sure you want to delete the template "${template.title}"? This action cannot be undone.`;

        if (!confirm(confirmMessage)) return;

        try {
            await this.deleteTemplate(template.id);

            // Remove from local state
            const updatedTemplates = this.state.templates.filter(t => t.id !== template.id);
            const updatedFiltered = this.state.filteredTemplates.filter(t => t.id !== template.id);

            this.setState({
                templates: updatedTemplates,
                filteredTemplates: updatedFiltered,
                selectedTemplate: null
            });

            // Clear details panel
            if (this.refs.detailsPanel) {
                this.refs.detailsPanel.innerHTML = '<div class="no-selection">Select a template to view details</div>';
            }

            this.renderTemplates();
            this.emit('templates:templateDeleted', template);

        } catch (error) {
            this.showError(error);
            this.emit('templates:deleteError', error);
        }
    }

    /**
     * Delete template via API
     */
    async deleteTemplate(templateId) {
        const response = await fetch(`${this.options.apiEndpoint}/${templateId}`, {
            method: 'DELETE',
            headers: {
                'Accept': 'application/json',
                ...(window.ChronosAPI?.getAuthHeaders?.() || {})
            }
        });

        if (!response.ok) {
            throw new Error(`Failed to delete template: ${response.status}`);
        }
    }

    /**
     * Handle keyboard navigation
     */
    handleKeydown(event) {
        if (!this.state.isOpen) return;

        switch (event.key) {
            case 'Escape':
                if (this.options.closeOnEscape) {
                    event.preventDefault();
                    this.close();
                }
                break;

            case 'ArrowDown':
                event.preventDefault();
                this.navigateTemplates(1);
                break;

            case 'ArrowUp':
                event.preventDefault();
                this.navigateTemplates(-1);
                break;

            case 'Enter':
                if (this.state.selectedTemplate && event.target === this.refs.searchInput) {
                    event.preventDefault();
                    this.handleApplyTemplate();
                }
                break;
        }
    }

    /**
     * Handle template item keyboard events
     */
    handleTemplateKeydown(event, index) {
        switch (event.key) {
            case 'Enter':
            case ' ':
                event.preventDefault();
                const template = this.state.filteredTemplates[index];
                if (template) {
                    this.selectTemplate(template, index);
                }
                break;

            case 'ArrowDown':
                event.preventDefault();
                this.navigateTemplates(1);
                break;

            case 'ArrowUp':
                event.preventDefault();
                this.navigateTemplates(-1);
                break;
        }
    }

    /**
     * Navigate through templates with keyboard
     */
    navigateTemplates(direction) {
        const { filteredTemplates, focusedIndex } = this.state;
        if (filteredTemplates.length === 0) return;

        let newIndex = focusedIndex + direction;

        // Wrap around
        if (newIndex < 0) {
            newIndex = filteredTemplates.length - 1;
        } else if (newIndex >= filteredTemplates.length) {
            newIndex = 0;
        }

        const template = filteredTemplates[newIndex];
        if (template) {
            this.selectTemplate(template, newIndex);

            // Focus the element
            const templateElement = this.refs.templatesList.querySelector(`[data-index="${newIndex}"]`);
            if (templateElement) {
                templateElement.focus();
            }
        }
    }

    /**
     * Handle load errors
     */
    handleLoadError(error) {
        this.showError(error);

        if (this.refs.templatesList) {
            this.refs.templatesList.innerHTML = `
                <div class="error-state">
                    <div class="error-icon">⚠️</div>
                    <div class="error-title">Failed to load templates</div>
                    <div class="error-message">${this.escapeHtml(error.message || 'Unknown error')}</div>
                    <button class="retry-button" onclick="this.loadTemplates()">
                        Try Again
                    </button>
                </div>
            `;
        }
    }

    // Utility methods (same as EventList component)
    getSearchTokens(query) {
        return (query || '').trim().toLowerCase().split(/\s+/).filter(Boolean);
    }

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

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
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

    /**
     * Public API
     */
    isOpen() {
        return this.state.isOpen;
    }

    getSelectedTemplate() {
        return this.state.selectedTemplate;
    }

    getTemplates() {
        return [...this.state.templates];
    }

    setSearchQuery(query) {
        this.setState({ searchQuery: query });
        this.filterTemplates(query);

        if (this.refs.searchInput) {
            this.refs.searchInput.value = query;
        }
    }
}

// Register component globally
window.TemplateModalComponent = TemplateModalComponent;

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TemplateModalComponent;
}