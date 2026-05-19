/* Animation Utilities Script */

(function() {
    'use strict';

    class AnimationManager {
        constructor() {
            this.animations = new Map();
            this.init();
        }

        init() {
            this.setupIntersectionObserver();
            this.setupAnimationTriggers();
        }

        setupIntersectionObserver() {
            if (!window.IntersectionObserver) return;

            const animatedElements = document.querySelectorAll('[data-animate]');
            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const animation = entry.target.getAttribute('data-animate');
                        this.applyAnimation(entry.target, animation);
                        observer.unobserve(entry.target);
                    }
                });
            }, { threshold: 0.1 });

            animatedElements.forEach(el => observer.observe(el));
        }

        applyAnimation(element, animationName) {
            const delay = element.getAttribute('data-animation-delay') || '0';
            element.style.animationDelay = delay + 'ms';
            element.classList.add('animate-' + animationName);
        }

        setupAnimationTriggers() {
            document.addEventListener('propza:animate', (e) => {
                const { element, animation } = e.detail;
                if (element) {
                    this.applyAnimation(element, animation);
                }
            });
        }

        static fadeIn(element, duration = 300) {
            element.style.animation = `fadeIn ${duration}ms ease-in-out`;
        }

        static slideIn(element, direction = 'up', duration = 300) {
            const animationName = direction === 'left' ? 'slideInLeft' : 
                                 direction === 'right' ? 'slideInRight' : 'slideIn';
            element.style.animation = `${animationName} ${duration}ms ease-in-out`;
        }

        static scaleIn(element, duration = 300) {
            element.style.animation = `scaleIn ${duration}ms ease-in-out`;
        }

        static pulse(element) {
            element.classList.add('animate-pulse');
            setTimeout(() => element.classList.remove('animate-pulse'), 2000);
        }

        static bounce(element, times = 3) {
            let count = 0;
            const interval = setInterval(() => {
                element.style.animation = 'none';
                setTimeout(() => {
                    element.style.animation = 'bounce 1s';
                    count++;
                    if (count >= times) clearInterval(interval);
                }, 10);
            }, 1000);
        }

        static shake(element, duration = 500) {
            element.style.animation = `shake ${duration}ms ease-in-out`;
        }

        static highlightGlow(element, duration = 2000) {
            element.style.animation = `glow ${duration}ms ease-in-out`;
        }
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => new AnimationManager());
    } else {
        new AnimationManager();
    }

    // Export for global use
    window.AnimationManager = AnimationManager;
})();
