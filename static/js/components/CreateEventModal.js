/**
 * CreateEventModal Component - Modal for creating new events with template and calendar selection
 * Integrated with existing Chronos v2.2 architecture
 */
class CreateEventModalComponent extends ChronosComponent {

    get defaultOptions() {
        return {
            ...super.defaultOptions,
            className: 'create-event-modal-component',
            apiEndpoint: '/api/v1/events',
            calendarsEndpoint: '/api/v1/caldav/calendars',
            templatesEndpoint: '/api/v1/templates',
            autoFocus: true,
            closeOnBackdrop: true,
            closeOnEscape: true
        };
    }

    get defaultState() {
        return {
            ...super.defaultState,
            isOpen: false,
            calendars: [],
            templates: [],
            selectedCalendar: null,
            selectedTemplate: null,
            formData: {
                title: '',
                description: '',
                start_time: '',
                end_time: '',
                all_day: false,
                calendar_id: '',
                priority: 'MEDIUM',
                event_type: 'TASK',
                tags: [],
                attendees: [],
                location: ''
            },
            isSubmitting: false,
            validationErrors: {}
        };
    }

    setupDOMReferences() {
        super.setupDOMReferences();

        this.refs = {
            ...this.refs,
            modal: this.element.querySelector('[data-ref="modal"]') || this.element,
            backdrop: this.element.querySelector('[data-ref="backdrop"]'),
            form: this.element.querySelector('[data-ref="form"]'),
            titleInput: this.element.querySelector('[data-ref="title"]'),
            descriptionInput: this.element.querySelector('[data-ref="description"]'),
            startTimeInput: this.element.querySelector('[data-ref="start-time"]'),
            endTimeInput: this.element.querySelector('[data-ref="end-time"]'),
            allDayCheckbox: this.element.querySelector('[data-ref="all-day"]'),
            calendarSelect: this.element.querySelector('[data-ref="calendar"]'),
            templateSelect: this.element.querySelector('[data-ref="template"]'),
            prioritySelect: this.element.querySelector('[data-ref="priority"]'),
            eventTypeSelect: this.element.querySelector('[data-ref="event-type"]'),
            locationInput: this.element.querySelector('[data-ref="location"]'),
            tagsInput: this.element.querySelector('[data-ref="tags"]'),
            attendeesInput: this.element.querySelector('[data-ref="attendees"]'),
            saveButton: this.element.querySelector('[data-ref="save"]'),
            cancelButton: this.element.querySelector('[data-ref="cancel"]'),
            closeButton: this.element.querySelector('[data-ref="close"]'),
            useTemplateButton: this.element.querySelector('[data-ref="use-template"]')
        };
    }

    setupEventListeners() {
        super.setupEventListeners();

        // Form submission
        if (this.refs.form) {
            this.addEventListener(this.refs.form, 'submit', this.handleSubmit.bind(this));
        }

        // Save button
        if (this.refs.saveButton) {
            this.addEventListener(this.refs.saveButton, 'click', this.handleSave.bind(this));
        }

        // Cancel button
        if (this.refs.cancelButton) {
            this.addEventListener(this.refs.cancelButton, 'click', this.handleCancel.bind(this));
        }

        // Close button
        if (this.refs.closeButton) {
            this.addEventListener(this.refs.closeButton, 'click', this.close.bind(this));
        }

        // Template selection
        if (this.refs.templateSelect) {
            this.addEventListener(this.refs.templateSelect, 'change', this.handleTemplateChange.bind(this));
        }

        // Use template button
        if (this.refs.useTemplateButton) {
            this.addEventListener(this.refs.useTemplateButton, 'click', this.handleUseTemplate.bind(this));
        }

        // All-day checkbox
        if (this.refs.allDayCheckbox) {
            this.addEventListener(this.refs.allDayCheckbox, 'change', this.handleAllDayChange.bind(this));
        }

        // Form field changes
        const formFields = ['titleInput', 'descriptionInput', 'startTimeInput', 'endTimeInput',
                           'calendarSelect', 'prioritySelect', 'eventTypeSelect', 'locationInput',
                           'tagsInput', 'attendeesInput'];

        formFields.forEach(fieldRef => {
            if (this.refs[fieldRef]) {
                this.addEventListener(this.refs[fieldRef], 'input', this.handleFieldChange.bind(this));
                this.addEventListener(this.refs[fieldRef], 'change', this.handleFieldChange.bind(this));
            }
        });

        // Backdrop click
        if (this.refs.backdrop && this.options.closeOnBackdrop) {
            this.addEventListener(this.refs.backdrop, 'click', (e) => {
                if (e.target === this.refs.backdrop) {
                    this.handleCancel();
                }
            });
        }

        // Keyboard events
        if (this.options.closeOnEscape) {
            this.addEventListener(document, 'keydown', this.handleKeydown.bind(this));
        }

        // Global events
        this.subscribe('createEvent:open', this.open.bind(this));
        this.subscribe('createEvent:close', this.close.bind(this));
        this.subscribe('calendars:refresh', this.loadCalendars.bind(this));
        this.subscribe('templates:refresh', this.loadTemplates.bind(this));
    }

    /**
     * Open the modal
     */
    async open(options = {}) {
        if (this.state.isOpen) return;

        this.setState({
            isOpen: true,
            formData: { ...this.defaultState.formData, ...options.formData },
            validationErrors: {}
        });

        // Show modal
        this.refs.modal.showModal?.() || this.showModal();

        // Load data
        await Promise.all([
            this.loadCalendars(),
            this.loadTemplates()
        ]);

        // Set default values
        if (options.calendar_id) {
            this.setState(state => ({
                formData: { ...state.formData, calendar_id: options.calendar_id }
            }));
        }

        // Focus management
        if (this.options.autoFocus && this.refs.titleInput) {
            this.refs.titleInput.focus();
        }

        // Prevent body scroll
        document.body.style.overflow = 'hidden';

        this.updateFormFields();
        this.emit('createEvent:opened');
    }

    /**
     * Close the modal
     */
    close() {
        if (!this.state.isOpen) return;

        this.setState({
            isOpen: false,
            selectedTemplate: null,
            formData: { ...this.defaultState.formData },
            validationErrors: {},
            isSubmitting: false
        });

        // Hide modal
        this.refs.modal.close?.() || this.hideModal();

        // Restore body scroll
        document.body.style.overflow = '';

        this.emit('createEvent:closed');
    }

    /**
     * Show modal (fallback)
     */
    showModal() {
        this.element.style.display = 'flex';
        this.element.setAttribute('aria-modal', 'true');
        this.element.setAttribute('aria-hidden', 'false');
    }

    /**
     * Hide modal (fallback)
     */
    hideModal() {
        this.element.style.display = 'none';
        this.element.setAttribute('aria-modal', 'false');
        this.element.setAttribute('aria-hidden', 'true');
    }

    /**
     * Load available calendars
     */
    async loadCalendars() {
        try {
            const response = await this.fetchCalendars();
            this.setState({ calendars: response.calendars || [] });
            this.renderCalendarOptions();
        } catch (error) {
            this.handleLoadError('calendars', error);
        }
    }

    /**
     * Load available templates
     */
    async loadTemplates() {
        try {
            const response = await this.fetchTemplates();
            this.setState({ templates: response.items || [] });
            this.renderTemplateOptions();
        } catch (error) {
            this.handleLoadError('templates', error);
        }
    }

    /**
     * Fetch calendars from API
     */
    async fetchCalendars() {
        const response = await fetch(this.options.calendarsEndpoint, {
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
     * Fetch templates from API
     */
    async fetchTemplates() {
        const url = new URL(this.options.templatesEndpoint, window.location.origin);
        url.searchParams.append('page', '1');
        url.searchParams.append('page_size', '100');

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
     * Render calendar options
     */
    renderCalendarOptions() {
        if (!this.refs.calendarSelect) return;

        const { calendars, formData } = this.state;

        this.refs.calendarSelect.innerHTML = '';

        // Default option
        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = 'Kalender auswählen...';
        this.refs.calendarSelect.appendChild(defaultOption);

        // Calendar options
        calendars.forEach(calendar => {
            const option = document.createElement('option');
            option.value = calendar.id;
            option.textContent = calendar.alias || calendar.id;
            if (calendar.id === formData.calendar_id) {
                option.selected = true;
            }
            this.refs.calendarSelect.appendChild(option);
        });
    }

    /**
     * Render template options
     */
    renderTemplateOptions() {
        if (!this.refs.templateSelect) return;

        const { templates } = this.state;

        this.refs.templateSelect.innerHTML = '';

        // Default option
        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = 'Vorlage auswählen (optional)...';
        this.refs.templateSelect.appendChild(defaultOption);

        // Template options
        templates.forEach(template => {
            const option = document.createElement('option');
            option.value = template.id;
            option.textContent = `${template.title} (${template.usage_count || 0}×)`;
            this.refs.templateSelect.appendChild(option);
        });
    }

    /**
     * Handle form submission
     */
    async handleSubmit(event) {
        event.preventDefault();
        await this.handleSave();
    }

    /**
     * Handle save button click
     */
    async handleSave() {
        if (this.state.isSubmitting) return;

        const validationErrors = this.validateForm();
        if (Object.keys(validationErrors).length > 0) {
            this.setState({ validationErrors });
            this.showValidationErrors(validationErrors);
            return;
        }

        this.setState({ isSubmitting: true, validationErrors: {} });

        try {
            const eventData = this.prepareEventData();
            const createdEvent = await this.createEvent(eventData);

            this.emit('createEvent:success', createdEvent);
            this.close();
            this.showSuccess('Event erfolgreich erstellt');

        } catch (error) {
            this.handleSaveError(error);
        } finally {
            this.setState({ isSubmitting: false });
        }
    }

    /**
     * Handle cancel button click
     */
    handleCancel() {
        if (this.state.isSubmitting) return;

        const hasChanges = this.hasFormChanges();
        if (hasChanges) {
            if (!confirm('Möchten Sie wirklich abbrechen? Ihre Änderungen gehen verloren.')) {
                return;
            }
        }

        this.emit('createEvent:cancelled');
        this.close();
    }

    /**
     * Handle template change
     */
    handleTemplateChange(event) {
        const templateId = event.target.value;
        if (!templateId) {
            this.setState({ selectedTemplate: null });
            if (this.refs.useTemplateButton) {
                this.refs.useTemplateButton.disabled = true;
            }
            return;
        }

        const template = this.state.templates.find(t => t.id == templateId);
        if (template) {
            this.setState({ selectedTemplate: template });
            if (this.refs.useTemplateButton) {
                this.refs.useTemplateButton.disabled = false;
            }
        }
    }

    /**
     * Handle use template button
     */
    async handleUseTemplate() {
        const { selectedTemplate } = this.state;
        if (!selectedTemplate) return;

        try {
            // Record template usage
            await this.recordTemplateUsage(selectedTemplate.id);

            // Apply template to form
            const templateData = this.applyTemplate(selectedTemplate);
            this.setState(state => ({
                formData: { ...state.formData, ...templateData }
            }));

            this.updateFormFields();

            // Enable use template button
            if (this.refs.useTemplateButton) {
                this.refs.useTemplateButton.disabled = false;
            }

            this.emit('createEvent:templateApplied', selectedTemplate);
            this.showSuccess(`Vorlage "${selectedTemplate.title}" angewendet`);

        } catch (error) {
            this.showError(`Fehler beim Anwenden der Vorlage: ${error.message}`);
        }
    }

    /**
     * Apply template to form data
     */
    applyTemplate(template) {
        const templateData = {
            title: template.title || '',
            description: template.description || '',
            all_day: Boolean(template.all_day),
            calendar_id: template.calendar_id || this.state.formData.calendar_id
        };

        // Handle duration
        if (template.duration_minutes && !template.all_day) {
            const now = new Date();
            const startTime = template.default_time ?
                this.parseDefaultTime(template.default_time, now) : now;
            const endTime = new Date(startTime.getTime() + (template.duration_minutes * 60000));

            templateData.start_time = startTime.toISOString().slice(0, 16);
            templateData.end_time = endTime.toISOString().slice(0, 16);
        }

        // Handle tags
        if (template.tags && template.tags.length > 0) {
            templateData.tags = template.tags;
        }

        return templateData;
    }

    /**
     * Parse default time from template
     */
    parseDefaultTime(defaultTime, baseDate) {
        const [hours, minutes] = defaultTime.split(':').map(Number);
        const result = new Date(baseDate);
        result.setHours(hours, minutes, 0, 0);
        return result;
    }

    /**
     * Record template usage
     */
    async recordTemplateUsage(templateId) {
        const response = await fetch(`${this.options.templatesEndpoint}/${templateId}/use`, {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                ...(window.ChronosAPI?.getAuthHeaders?.() || {})
            }
        });

        if (!response.ok) {
            throw new Error(`Failed to record template usage: ${response.status}`);
        }

        return await response.json();
    }

    /**
     * Handle all-day checkbox change
     */
    handleAllDayChange(event) {
        const allDay = event.target.checked;
        this.setState(state => ({
            formData: { ...state.formData, all_day: allDay }
        }));

        // Show/hide time inputs
        if (this.refs.startTimeInput && this.refs.endTimeInput) {
            this.refs.startTimeInput.style.display = allDay ? 'none' : 'block';
            this.refs.endTimeInput.style.display = allDay ? 'none' : 'block';
        }
    }

    /**
     * Handle form field changes
     */
    handleFieldChange(event) {
        const { name, value, type, checked } = event.target;
        const fieldValue = type === 'checkbox' ? checked : value;

        this.setState(state => ({
            formData: {
                ...state.formData,
                [name]: fieldValue
            }
        }));

        // Clear validation error for this field
        if (this.state.validationErrors[name]) {
            this.setState(state => ({
                validationErrors: {
                    ...state.validationErrors,
                    [name]: undefined
                }
            }));
        }
    }

    /**
     * Handle keyboard events
     */
    handleKeydown(event) {
        if (!this.state.isOpen) return;

        switch (event.key) {
            case 'Escape':
                if (this.options.closeOnEscape) {
                    event.preventDefault();
                    this.handleCancel();
                }
                break;

            case 'Enter':
                if (event.ctrlKey || event.metaKey) {
                    event.preventDefault();
                    this.handleSave();
                }
                break;
        }
    }

    /**
     * Validate form data
     */
    validateForm() {
        const { formData } = this.state;
        const errors = {};

        // Title is required
        if (!formData.title.trim()) {
            errors.title = 'Titel ist erforderlich';
        }

        // Calendar is required
        if (!formData.calendar_id) {
            errors.calendar_id = 'Kalender ist erforderlich';
        }

        // Time validation for non-all-day events
        if (!formData.all_day) {
            if (!formData.start_time) {
                errors.start_time = 'Startzeit ist erforderlich';
            }
            if (!formData.end_time) {
                errors.end_time = 'Endzeit ist erforderlich';
            }
            if (formData.start_time && formData.end_time) {
                const startTime = new Date(formData.start_time);
                const endTime = new Date(formData.end_time);
                if (endTime <= startTime) {
                    errors.end_time = 'Endzeit muss nach der Startzeit liegen';
                }
            }
        }

        return errors;
    }

    /**
     * Show validation errors
     */
    showValidationErrors(errors) {
        // Clear previous error states
        this.element.querySelectorAll('.form-field-error').forEach(el => {
            el.classList.remove('form-field-error');
        });

        // Show new errors
        Object.keys(errors).forEach(fieldName => {
            const field = this.element.querySelector(`[name="${fieldName}"]`);
            if (field) {
                field.classList.add('form-field-error');
            }
        });

        // Show error message
        const firstError = Object.values(errors)[0];
        this.showError(firstError);
    }

    /**
     * Prepare event data for API
     */
    prepareEventData() {
        const { formData } = this.state;

        const eventData = {
            title: formData.title.trim(),
            description: formData.description.trim(),
            calendar_id: formData.calendar_id,
            priority: formData.priority,
            event_type: formData.event_type,
            location: formData.location.trim(),
            tags: this.parseTags(formData.tags),
            attendees: this.parseAttendees(formData.attendees)
        };

        // Handle all-day vs timed events
        if (formData.all_day) {
            eventData.all_day = true;
            if (formData.start_time) {
                const date = formData.start_time.split('T')[0];
                eventData.all_day_date = date;
            }
        } else {
            eventData.all_day = false;
            eventData.start_time = formData.start_time;
            eventData.end_time = formData.end_time;
        }

        return eventData;
    }

    /**
     * Parse tags input
     */
    parseTags(tagsString) {
        if (!tagsString) return [];
        return tagsString.split(',').map(tag => tag.trim()).filter(Boolean);
    }

    /**
     * Parse attendees input
     */
    parseAttendees(attendeesString) {
        if (!attendeesString) return [];
        return attendeesString.split(',').map(email => email.trim()).filter(Boolean);
    }

    /**
     * Create event via API
     */
    async createEvent(eventData) {
        const response = await fetch(this.options.apiEndpoint, {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                ...(window.ChronosAPI?.getAuthHeaders?.() || {})
            },
            body: JSON.stringify(eventData)
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to create event: ${response.status} ${errorText}`);
        }

        return await response.json();
    }

    /**
     * Update form fields with current state
     */
    updateFormFields() {
        const { formData } = this.state;

        Object.keys(formData).forEach(key => {
            const field = this.element.querySelector(`[name="${key}"]`);
            if (field) {
                if (field.type === 'checkbox') {
                    field.checked = formData[key];
                } else if (Array.isArray(formData[key])) {
                    field.value = formData[key].join(', ');
                } else {
                    field.value = formData[key] || '';
                }
            }
        });

        // Handle all-day display
        this.handleAllDayChange({ target: { checked: formData.all_day } });
    }

    /**
     * Check if form has changes
     */
    hasFormChanges() {
        const { formData } = this.state;
        const defaultData = this.defaultState.formData;

        return Object.keys(formData).some(key => {
            return JSON.stringify(formData[key]) !== JSON.stringify(defaultData[key]);
        });
    }

    /**
     * Handle save errors
     */
    handleSaveError(error) {
        this.showError(`Fehler beim Erstellen des Events: ${error.message}`);
        this.emit('createEvent:error', error);
    }

    /**
     * Handle load errors
     */
    handleLoadError(type, error) {
        this.showError(`Fehler beim Laden der ${type}: ${error.message}`);
    }

    /**
     * Show success message
     */
    showSuccess(message) {
        // This would integrate with the existing toast/notification system
        if (window.showToast) {
            window.showToast('Erfolg', message, 'success');
        } else {
            console.log('Success:', message);
        }
    }

    /**
     * Show error message
     */
    showError(message) {
        // This would integrate with the existing toast/notification system
        if (window.showToast) {
            window.showToast('Fehler', message, 'error');
        } else {
            console.error('Error:', message);
        }
    }

    /**
     * Public API
     */
    isOpen() {
        return this.state.isOpen;
    }

    getFormData() {
        return { ...this.state.formData };
    }

    setFormData(data) {
        this.setState(state => ({
            formData: { ...state.formData, ...data }
        }));
        this.updateFormFields();
    }

    clearForm() {
        this.setState({
            formData: { ...this.defaultState.formData },
            selectedTemplate: null,
            validationErrors: {}
        });
        this.updateFormFields();
    }
}

// Register component globally
window.CreateEventModalComponent = CreateEventModalComponent;

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CreateEventModalComponent;
}