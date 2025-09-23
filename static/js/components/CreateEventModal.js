/**
 * CreateEventModal Component - Simple modal for creating new events
 * Standalone implementation without base class dependencies
 */
class CreateEventModalComponent {
    constructor(element, options = {}) {
        this.element = element;
        this.options = {
            apiEndpoint: '/api/v1/events',
            calendarsEndpoint: '/api/v1/caldav/calendars',
            templatesEndpoint: '/api/v1/templates',
            ...options
        };

        this.isOpen = false;
        this.calendars = [];
        this.templates = [];
        this.eventListeners = {};

        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadCalendars();
        this.loadTemplates();
    }

    setupEventListeners() {
        // Close button
        const closeBtn = this.element.querySelector('[data-ref="close"]');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.close());
        }

        // Cancel button
        const cancelBtn = this.element.querySelector('[data-ref="cancel"]');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => this.close());
        }

        // Backdrop click to close
        const backdrop = this.element.querySelector('.modal-backdrop');
        if (backdrop) {
            backdrop.addEventListener('click', () => this.close());
        }

        // Escape key to close
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isOpen) {
                this.close();
            }
        });

        // Form submission
        const form = this.element.querySelector('form');
        if (form) {
            form.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleSubmit();
            });
        }

        // Save button
        const saveBtn = this.element.querySelector('[data-ref="save"]');
        if (saveBtn) {
            saveBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleSubmit();
            });
        }

        // Template selection
        const templateSelect = this.element.querySelector('[data-ref="template"]');
        if (templateSelect) {
            templateSelect.addEventListener('change', (e) => {
                this.applyTemplate(e.target.value);
            });
        }

        // All-day checkbox logic
        const allDayCheckbox = this.element.querySelector('[data-ref="all-day"]');
        const startTimeInput = this.element.querySelector('[data-ref="start-time"]');
        const endTimeInput = this.element.querySelector('[data-ref="end-time"]');

        if (allDayCheckbox && startTimeInput && endTimeInput) {
            allDayCheckbox.addEventListener('change', (e) => {
                const isAllDay = e.target.checked;
                startTimeInput.disabled = isAllDay;
                endTimeInput.disabled = isAllDay;

                if (isAllDay) {
                    // Clear time inputs when all-day is selected
                    startTimeInput.value = '';
                    endTimeInput.value = '';
                }
            });
        }
    }

    async loadCalendars() {
        try {
            const response = await fetch(this.options.calendarsEndpoint);
            const data = await response.json();

            if (data.success && data.calendars) {
                this.calendars = data.calendars;
                this.populateCalendarSelect();
            }
        } catch (error) {
            console.error('Failed to load calendars:', error);
        }
    }

    async loadTemplates() {
        try {
            const response = await fetch(this.options.templatesEndpoint);
            const data = await response.json();

            if (data.success && data.templates) {
                this.templates = data.templates;
                this.populateTemplateSelect();
            }
        } catch (error) {
            console.error('Failed to load templates:', error);
        }
    }

    populateCalendarSelect() {
        const select = this.element.querySelector('[data-ref="calendar"]');
        if (!select) return;

        // Clear existing options
        select.innerHTML = '<option value="">Kalender wählen...</option>';

        // Add calendar options
        this.calendars.forEach(calendar => {
            const option = document.createElement('option');
            option.value = calendar.alias || calendar.id;
            option.textContent = calendar.name;
            select.appendChild(option);
        });
    }

    populateTemplateSelect() {
        const select = this.element.querySelector('[data-ref="template"]');
        if (!select) return;

        // Clear existing options
        select.innerHTML = '<option value="">Vorlage wählen (optional)...</option>';

        // Add template options
        this.templates.forEach(template => {
            const option = document.createElement('option');
            option.value = template.id;
            option.textContent = template.name;
            select.appendChild(option);
        });
    }

    applyTemplate(templateId) {
        if (!templateId) return;

        const template = this.templates.find(t => t.id === templateId);
        if (!template) return;

        // Apply template defaults to form
        if (template.defaults) {
            if (template.defaults.title) {
                const titleInput = this.element.querySelector('[data-ref="title"]');
                if (titleInput) titleInput.value = template.defaults.title;
            }

            if (template.defaults.description) {
                const descInput = this.element.querySelector('[data-ref="description"]');
                if (descInput) descInput.value = template.defaults.description;
            }
        }

        // Set default duration if provided
        if (template.default_duration && !this.element.querySelector('[data-ref="start-time"]').value) {
            this.setDefaultTimes(template.default_duration);
        }
    }

    setDefaultTimes(durationMinutes) {
        const now = new Date();
        const start = new Date(now);
        start.setMinutes(0, 0, 0); // Round to hour
        start.setHours(start.getHours() + 1); // Next hour

        const end = new Date(start);
        end.setMinutes(end.getMinutes() + durationMinutes);

        const startInput = this.element.querySelector('[data-ref="start-time"]');
        const endInput = this.element.querySelector('[data-ref="end-time"]');

        if (startInput) {
            startInput.value = this.formatDateTimeLocal(start);
        }

        if (endInput) {
            endInput.value = this.formatDateTimeLocal(end);
        }
    }

    formatDateTimeLocal(date) {
        // Format for datetime-local input: YYYY-MM-DDTHH:MM
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');

        return `${year}-${month}-${day}T${hours}:${minutes}`;
    }

    async handleSubmit() {
        const formData = this.getFormData();

        // Basic validation
        if (!formData.title.trim()) {
            alert('Titel ist erforderlich');
            return;
        }

        if (!formData.calendar_id) {
            alert('Kalender auswählen ist erforderlich');
            return;
        }

        if (!formData.all_day && (!formData.start_time || !formData.end_time)) {
            alert('Start- und Endzeit sind erforderlich (außer bei ganztägigen Events)');
            return;
        }

        try {
            const response = await fetch(this.options.apiEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            });

            const result = await response.json();

            if (result.success) {
                this.dispatchEvent('createEvent:success', { event: result.event });
                this.close();
                this.resetForm();
                alert('Event erfolgreich erstellt!');
            } else {
                throw new Error(result.message || 'Event creation failed');
            }
        } catch (error) {
            console.error('Failed to create event:', error);
            alert('Fehler beim Erstellen des Events: ' + error.message);
        }
    }

    getFormData() {
        const startTimeRaw = this.element.querySelector('[data-ref="start-time"]')?.value || '';
        const endTimeRaw = this.element.querySelector('[data-ref="end-time"]')?.value || '';
        const allDay = this.element.querySelector('[data-ref="all-day"]')?.checked || false;

        // Convert datetime-local format to ISO format for API
        const startTime = startTimeRaw ? new Date(startTimeRaw).toISOString() : '';
        const endTime = endTimeRaw ? new Date(endTimeRaw).toISOString() : '';

        // Parse tags and attendees from comma-separated strings
        const tagsRaw = this.element.querySelector('[data-ref="tags"]')?.value || '';
        const attendeesRaw = this.element.querySelector('[data-ref="attendees"]')?.value || '';

        const tags = tagsRaw ? tagsRaw.split(',').map(tag => tag.trim()).filter(tag => tag) : [];
        const attendees = attendeesRaw ? attendeesRaw.split(',').map(email => email.trim()).filter(email => email) : [];

        return {
            title: this.element.querySelector('[data-ref="title"]')?.value || '',
            description: this.element.querySelector('[data-ref="description"]')?.value || '',
            start_time: startTime,
            end_time: endTime,
            all_day: allDay,
            location: this.element.querySelector('[data-ref="location"]')?.value || '',
            priority: this.element.querySelector('[data-ref="priority"]')?.value || 'MEDIUM',
            event_type: this.element.querySelector('[data-ref="event-type"]')?.value || 'TASK',
            calendar_id: this.element.querySelector('[data-ref="calendar"]')?.value || '',
            template_id: this.element.querySelector('[data-ref="template"]')?.value || null,
            tags: tags,
            attendees: attendees
        };
    }

    resetForm() {
        const form = this.element.querySelector('form');
        if (form) {
            form.reset();
        }
    }

    open(options = {}) {
        this.isOpen = true;
        this.element.style.display = 'flex';

        // Apply any initial form data
        if (options.formData) {
            this.setFormData(options.formData);
        }

        // Focus first input
        const firstInput = this.element.querySelector('input, select, textarea');
        if (firstInput) {
            setTimeout(() => firstInput.focus(), 100);
        }

        this.dispatchEvent('modal:open');
    }

    close() {
        this.isOpen = false;
        this.element.style.display = 'none';
        this.dispatchEvent('modal:close');
    }

    setFormData(data) {
        Object.keys(data).forEach(key => {
            const input = this.element.querySelector(`[data-ref="${key}"]`) ||
                         this.element.querySelector(`[name="${key}"]`);
            if (input && data[key] !== undefined) {
                input.value = data[key];
            }
        });
    }

    // Simple event system
    addEventListener(event, callback) {
        if (!this.eventListeners[event]) {
            this.eventListeners[event] = [];
        }
        this.eventListeners[event].push(callback);
    }

    dispatchEvent(event, data = {}) {
        if (this.eventListeners[event]) {
            this.eventListeners[event].forEach(callback => {
                callback({ type: event, detail: data });
            });
        }
    }
}

// Make sure the component is available globally
window.CreateEventModalComponent = CreateEventModalComponent;