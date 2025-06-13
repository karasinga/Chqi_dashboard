document.addEventListener('DOMContentLoaded', function () {
    // Function to close any open modal
    function closeModal() {
        const openModal = document.querySelector('.modal.show');
        if (openModal) {
            const modal = bootstrap.Modal.getInstance(openModal);
            if (modal) {
                modal.hide();
            }
        }
    }

    // Listen for the custom event to close the modal
    document.body.addEventListener('close-modal', closeModal);
});