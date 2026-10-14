(function () {
    "use strict";

    const STORAGE_KEY = "hcp-theme";
    const root = document.documentElement;

    function lireTheme() {
        try {
            const themeHcp = localStorage.getItem(
                STORAGE_KEY
            );

            const themeDjango = localStorage.getItem(
                "theme"
            );

            if (
                themeHcp === "dark"
                || themeDjango === "dark"
            ) {
                return "dark";
            }
        } catch (error) {
            console.warn(
                "Impossible de lire le thème enregistré.",
                error
            );
        }

        return "light";
    }


    function mettreAJourBouton(theme) {
        const bouton = document.getElementById(
            "hcp-theme-toggle"
        );

        if (!bouton) {
            return;
        }

        const symbole = bouton.querySelector(
            "[data-theme-symbol]"
        );

        const modeSombre = theme === "dark";

        bouton.setAttribute(
            "aria-label",
            modeSombre
                ? "Activer le mode clair"
                : "Activer le mode sombre"
        );

        bouton.setAttribute(
            "title",
            modeSombre
                ? "Mode clair"
                : "Mode sombre"
        );

        bouton.setAttribute(
            "aria-pressed",
            modeSombre ? "true" : "false"
        );

        if (symbole) {
            symbole.textContent = modeSombre
                ? "☀"
                : "☾";
        }
    }


    function appliquerTheme(
        theme,
        enregistrer = true
    ) {
        const themeFinal = (
            theme === "dark"
            ? "dark"
            : "light"
        );

        root.setAttribute(
            "data-theme",
            themeFinal
        );

        root.setAttribute(
            "data-bs-theme",
            themeFinal
        );

        document.body?.setAttribute(
            "data-theme",
            themeFinal
        );

        if (enregistrer) {
            try {
                localStorage.setItem(
                    STORAGE_KEY,
                    themeFinal
                );

                /*
                 * Synchronisation avec le système
                 * de thème intégré à Django Admin.
                 */
                localStorage.setItem(
                    "theme",
                    themeFinal
                );
            } catch (error) {
                console.warn(
                    "Impossible d'enregistrer le thème.",
                    error
                );
            }
        }

        const couleurTheme = document.querySelector(
            'meta[name="theme-color"]'
        );

        if (couleurTheme) {
            couleurTheme.setAttribute(
                "content",
                themeFinal === "dark"
                    ? "#11141b"
                    : "#74133f"
            );
        }

        mettreAJourBouton(
            themeFinal
        );

        window.dispatchEvent(
            new CustomEvent(
                "hcp-theme-changed",
                {
                    detail: {
                        theme: themeFinal,
                    },
                }
            )
        );
    }


    appliquerTheme(
        lireTheme(),
        false
    );


    document.addEventListener(
        "DOMContentLoaded",
        function () {
            const bouton = document.getElementById(
                "hcp-theme-toggle"
            );

            mettreAJourBouton(
                lireTheme()
            );

            if (!bouton) {
                return;
            }

            bouton.addEventListener(
                "click",
                function () {
                    const themeActuel = (
                        root.getAttribute(
                            "data-theme"
                        ) === "dark"
                        ? "dark"
                        : "light"
                    );

                    appliquerTheme(
                        themeActuel === "dark"
                            ? "light"
                            : "dark"
                    );
                }
            );
        }
    );
})();