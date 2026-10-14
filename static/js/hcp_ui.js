document.addEventListener(
    "DOMContentLoaded",
    function () {
        const tooltips =
            document.querySelectorAll(
                '[data-bs-toggle="tooltip"]'
            );

        tooltips.forEach(
            function (element) {
                new bootstrap.Tooltip(
                    element
                );
            }
        );

        document.querySelectorAll(
            "[data-confirm-message]"
        ).forEach(
            function (element) {
                element.addEventListener(
                    "click",
                    function (event) {
                        const message =
                            element.dataset
                                .confirmMessage;

                        if (
                            message
                            && !window.confirm(
                                message
                            )
                        ) {
                            event.preventDefault();
                        }
                    }
                );
            }
        );
    }
);
