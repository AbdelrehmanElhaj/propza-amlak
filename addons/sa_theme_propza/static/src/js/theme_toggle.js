/* Theme Toggle Script */

(function() {
    'use strict';

    class ThemeToggle {
        constructor() {
            this.storageKey = 'propza-theme-preference';
            this.darkModeClass = 'dark-mode';
            this.init();
        }

        init() {
            this.setupToggleButton();
            this.loadThemePreference();
            this.setupSystemThemeListener();
        }

        setupToggleButton() {
            const buttons = document.querySelectorAll('[data-toggle-theme], .theme-toggle');
            buttons.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.toggle();
                });
            });
        }

        toggle() {
            const isDarkMode = this.isDarkMode();
            if (isDarkMode) {
                this.setTheme('light');
            } else {
                this.setTheme('dark');
            }
        }

        setTheme(theme) {
            if (theme === 'dark') {
                document.documentElement.setAttribute('data-theme', 'dark');
                document.body.classList.add(this.darkModeClass);
            } else {
                document.documentElement.setAttribute('data-theme', 'light');
                document.body.classList.remove(this.darkModeClass);
            }
            localStorage.setItem(this.storageKey, theme);
            this.dispatchThemeChangeEvent(theme);
        }

        isDarkMode() {
            return document.body.classList.contains(this.darkModeClass);
        }

        loadThemePreference() {
            const savedTheme = localStorage.getItem(this.storageKey);
            if (savedTheme) {
                this.setTheme(savedTheme);
            } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
                this.setTheme('dark');
            }
        }

        setupSystemThemeListener() {
            if (window.matchMedia) {
                const darkModeQuery = window.matchMedia('(prefers-color-scheme: dark)');
                darkModeQuery.addListener((e) => {
                    if (!localStorage.getItem(this.storageKey)) {
                        this.setTheme(e.matches ? 'dark' : 'light');
                    }
                });
            }
        }

        dispatchThemeChangeEvent(theme) {
            const event = new CustomEvent('propza-theme-changed', {
                detail: { theme: theme }
            });
            document.dispatchEvent(event);
        }
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => new ThemeToggle());
    } else {
        new ThemeToggle();
    }

    // Export for global use
    window.ThemeToggle = ThemeToggle;
})();
