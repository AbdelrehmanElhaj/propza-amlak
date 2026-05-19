/* Propza Modern Theme - Main Theme Script */

(function() {
    'use strict';

    const PropsaTheme = {
        storageKey: 'propza-theme-mode',
        darkModeClass: 'dark-mode',

        init: function() {
            this.detectRTL();
            this.detectSystemTheme();
            this.loadSavedTheme();
            this.setupThemeToggle();
            this.setupThemeObserver();
        },

        detectSystemTheme: function() {
            if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
                document.documentElement.setAttribute('data-theme', 'dark');
            } else {
                document.documentElement.setAttribute('data-theme', 'light');
            }
        },

        loadSavedTheme: function() {
            const savedTheme = localStorage.getItem(this.storageKey);
            if (savedTheme === 'dark') {
                this.enableDarkMode();
            } else if (savedTheme === 'light') {
                this.disableDarkMode();
            }
        },

        detectRTL: function() {
            const html = document.documentElement;
            const lang = (html.getAttribute('lang') || '').toLowerCase();
            const isRTL = html.getAttribute('dir') === 'rtl' || /^ar|fa|he|ur/.test(lang);
            if (isRTL) {
                html.setAttribute('dir', 'rtl');
                document.body.classList.add('rtl');
            }
        },

        enableDarkMode: function() {
            document.body.classList.add(this.darkModeClass);
            localStorage.setItem(this.storageKey, 'dark');
            document.documentElement.setAttribute('data-theme', 'dark');
        },

        disableDarkMode: function() {
            document.body.classList.remove(this.darkModeClass);
            localStorage.setItem(this.storageKey, 'light');
            document.documentElement.setAttribute('data-theme', 'light');
        },

        toggle: function() {
            if (document.body.classList.contains(this.darkModeClass)) {
                this.disableDarkMode();
            } else {
                this.enableDarkMode();
            }
        },

        setupThemeToggle: function() {
            const toggleBtn = document.querySelector('.theme-toggle');
            if (toggleBtn) {
                toggleBtn.addEventListener('click', () => this.toggle());
            }
        },

        setupThemeObserver: function() {
            if (window.matchMedia) {
                window.matchMedia('(prefers-color-scheme: dark)').addListener((e) => {
                    if (e.matches && !localStorage.getItem(this.storageKey)) {
                        this.enableDarkMode();
                    } else if (!e.matches && !localStorage.getItem(this.storageKey)) {
                        this.disableDarkMode();
                    }
                });
            }
        },

        getCurrentTheme: function() {
            return document.body.classList.contains(this.darkModeClass) ? 'dark' : 'light';
        }
    };

    // Initialize theme when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => PropsaTheme.init());
    } else {
        PropsaTheme.init();
    }

    // Export for global use
    window.PropsaTheme = PropsaTheme;
})();
