document.addEventListener('DOMContentLoaded', function () {

    function initializeGlobalEventListeners() {
        // Progress bars
        document.querySelectorAll('.progress-bar[data-completion]').forEach(bar => {
            bar.style.width = `${bar.dataset.completion}%`;
        });

        // Initialize dashboard-specific scripts if the dashboard content is present
        if (document.getElementById('filterForm')) {
            if (typeof initializeDashboard === 'function') {
                initializeDashboard();
            }
        }
    }

    // Prepare the modal for creating a new evaluation
    window.prepareCreateModal = function () {
        document.getElementById('modalTitle').textContent = 'Create New Evaluation';
        document.getElementById('projectId').value = '';
        document.getElementById('evaluationForm').reset();
    }

    // Prepare the modal for editing an evaluation
    window.prepareEditModal = function (projectId, projectData) {
        document.getElementById('modalTitle').textContent = 'Edit Evaluation';
        document.getElementById('projectId').value = projectId;

        const form = document.getElementById('evaluationForm');
        form.title.value = projectData.title;
        form.description.value = projectData.description;
        form.status.value = projectData.status;
        form.start_date.value = projectData.start_date;
        form.end_date.value = projectData.end_date || '';
        if (projectData.lead_researcher) {
            form.lead_researcher.value = projectData.lead_researcher;
        }
    }

    // Initial load
    initializeGlobalEventListeners();

    // Use MutationObserver to detect dynamically added content
    const observer = new MutationObserver(mutations => {
        mutations.forEach(mutation => {
            if (mutation.addedNodes.length) {
                initializeGlobalEventListeners();
            }
        });
    });

    observer.observe(document.body, { childList: true, subtree: true });
});
