/**
 * Baseline Filters JavaScript - Hybrid Approach
 * Combines excellent TomSelect integration with simplified HTMX handling
 * Implements debounced filter updates for improved UX
 */

class BaselineFilters {
    constructor(formId = 'baseline-filters') {
        this.form = document.getElementById(formId);
        if (!this.form) {
            console.error('Baseline filters form not found');
            return;
        }

        this.debounceDelay = 500; // 500ms delay
        this.debounceTimer = null;
        this.isRequestInProgress = false;

        this.initializeEventListeners();
        console.log('Baseline filters initialized with enhanced debouncing');
    }

    /**
     * Initialize event listeners for all filter selects
     */
    initializeEventListeners() {
        const filterSelects = this.form.querySelectorAll('select[multiple]');
        filterSelects.forEach(select => {
            select.addEventListener('change', (e) => {
                this.handleFilterChange(e);
            });
        });

        // Listen for HTMX events to track request state
        this.form.addEventListener('htmx:beforeRequest', () => {
            this.isRequestInProgress = true;
        });

        this.form.addEventListener('htmx:afterRequest', () => {
            this.isRequestInProgress = false;
        });
    }

    /**
     * Handle filter change with debouncing
     */
    handleFilterChange(event) {
        // Add debugging
        if (event && event.target) {
            console.log('Filter changed:', event.target.name, 'New values:', 
                event.target.tomselect ? event.target.tomselect.getValue() : 
                Array.from(event.target.selectedOptions).map(o => o.value)
            );
        }

        // Clear existing timer
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }

        // If a request is already in progress, ignore this change
        if (this.isRequestInProgress) {
            return;
        }

        // Set loading state
        this.setLoadingState(true);

        // Debounce the actual request
        this.debounceTimer = setTimeout(() => {
            this.triggerFilterUpdate();
        }, this.debounceDelay);
    }

    /**
     * Sync all TomSelect instances with their native select elements
     */
    syncAllFilters() {
        const allSelects = this.form.querySelectorAll('select[multiple]');
        allSelects.forEach(select => {
            if (select.tomselect) {
                select.tomselect.sync();
            }
        });
    }

    /**
     * Trigger the HTMX filter update
     */
    triggerFilterUpdate() {
        if (this.isRequestInProgress) {
            return;
        }

        // Force sync all TomSelect instances before getting form data
        this.syncAllFilters();

        // Get form data and convert to URL parameters
        const formData = new FormData(this.form);
        const params = new URLSearchParams();

        // Add existing URL parameters (like tab)
        const currentUrl = new URL(window.location.href);
        for (let [key, value] of currentUrl.searchParams) {
            params.append(key, value);
        }

        // Add form data
        for (let [key, value] of formData.entries()) {
            if (value) { // Only add non-empty values
                params.append(key, value);
            }
        }

        // Update the form's hx-get attribute with the new parameters
        const baseUrl = this.form.getAttribute('hx-get').split('?')[0];
        this.form.setAttribute('hx-get', baseUrl + '?' + params.toString());

        // Trigger HTMX request manually
        htmx.ajax('GET', this.form.getAttribute('hx-get'), {
            target: this.form.getAttribute('hx-target'),
            swap: this.form.getAttribute('hx-swap')
        });

        // Reset flags and loading state after a short delay
        setTimeout(() => {
            this.setLoadingState(false);
            this.isRequestInProgress = false;
        }, 100);
    }

    /**
     * Set loading state for the filter form
     */
    setLoadingState(isLoading) {
        const overlay = this.form.querySelector('.filter-loading-overlay');
        if (overlay) {
            if (isLoading) {
                overlay.style.opacity = '1';
                overlay.style.pointerEvents = 'auto';
            } else {
                overlay.style.opacity = '0';
                overlay.style.pointerEvents = 'none';
            }
        }
    }

    /**
     * Get current filter values as FormData
     */
    getCurrentFilterValues() {
        // Sync TomSelect instances first
        this.syncAllFilters();
        
        const values = {};

        // Get all select elements
        const allSelects = this.form.querySelectorAll('select[multiple]');
        
        allSelects.forEach(select => {
            const name = select.getAttribute('name');
            values[name] = [];
            
            // If TomSelect exists, get values from it
            if (select.tomselect) {
                const tomSelectValues = select.tomselect.getValue();
                if (Array.isArray(tomSelectValues)) {
                    values[name] = tomSelectValues;
                } else if (tomSelectValues) {
                    values[name] = [tomSelectValues];
                }
            } else {
                // Fallback to native select
                for (let i = 0; i < select.options.length; i++) {
                    if (select.options[i].selected) {
                        values[name].push(select.options[i].value);
                    }
                }
            }
        });

        console.log('Current filter values:', values);
        return values;
    }

    /**
     * Apply a saved filter state to the form
     */
    applyFilterState(filterState) {
        console.log('Applying filter state:', filterState);

        // Clear all current selections
        const allSelects = this.form.querySelectorAll('select[multiple]');
        allSelects.forEach(select => {
            // Clear native select options
            for (let i = 0; i < select.options.length; i++) {
                select.options[i].selected = false;
            }

            // Clear TomSelect if it exists
            if (select.tomselect) {
                select.tomselect.clear();
            }
        });

        // Apply the saved state with a small delay between each filter
        let delay = 0;
        for (const [filterName, values] of Object.entries(filterState)) {
            setTimeout(() => {
                const selectElement = this.form.querySelector(`select[name="${filterName}"]`);
                if (selectElement && values.length > 0) {
                    console.log(`Setting ${filterName} to:`, values);

                    // Update native select options first
                    for (let i = 0; i < selectElement.options.length; i++) {
                        const option = selectElement.options[i];
                        if (values.includes(option.value)) {
                            option.selected = true;
                        }
                    }

                    // Update TomSelect if it exists
                    if (selectElement.tomselect) {
                        // Use sync() to ensure TomSelect reflects the native select state
                        selectElement.tomselect.sync();
                        // Then set the values
                        selectElement.tomselect.setValue(values);
                    }

                    // Trigger change event
                    const changeEvent = new Event('change', { bubbles: true });
                    selectElement.dispatchEvent(changeEvent);
                }
            }, delay);
            delay += 50; // Stagger updates by 50ms
        }

        console.log('Filter state applied');
    }

    /**
     * Force immediate update (for reset functions)
     */
    forceUpdate() {
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }
        this.triggerFilterUpdate();
    }
}

// Global functions for backward compatibility with existing reset functions
let baselineFiltersInstance = null;

/**
 * Initialize baseline filters when DOM is ready
 */
document.addEventListener('DOMContentLoaded', function() {
    baselineFiltersInstance = new BaselineFilters();
});

/**
 * Resets a SINGLE filter to select all its options.
 */
function resetFilterToAll(selectId) {
    const selectElement = document.getElementById(selectId);
    if (!selectElement) return;

    // Select all options
    for (let i = 0; i < selectElement.options.length; i++) {
        selectElement.options[i].selected = true;
    }

    // If TomSelect exists, sync it
    if (selectElement.tomselect) {
        selectElement.tomselect.sync();
    }

    // Trigger change event to update TomSelect
    const event = new Event('change', { 'bubbles': true });
    selectElement.dispatchEvent(event);

    // Force immediate update if instance exists
    if (baselineFiltersInstance) {
        baselineFiltersInstance.forceUpdate();
    }
}

/**
 * Resets ALL filters in the form to select all their options.
 */
function resetAllFilters(buttonElement) {
    // Find the form that this button belongs to
    const form = buttonElement.closest('form');
    if (!form) return;

    // Find all multi-select elements within this form
    const allSelects = form.querySelectorAll('select[multiple]');

    // Loop through each select element and select all its options
    allSelects.forEach(selectElement => {
        for (let i = 0; i < selectElement.options.length; i++) {
            selectElement.options[i].selected = true;
        }
        
        // If TomSelect exists, sync it
        if (selectElement.tomselect) {
            selectElement.tomselect.sync();
        }
        
        // Trigger change event for each select
        const event = new Event('change', { 'bubbles': true });
        selectElement.dispatchEvent(event);
    });

    // Force immediate update if instance exists
    if (baselineFiltersInstance) {
        baselineFiltersInstance.forceUpdate();
    }
}

// Export for potential use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = BaselineFilters;
}
