/* ===========================
   PROPZA THEME - Property Components JavaScript
   =========================== */

(function() {
    'use strict';

    class PropertyComponents {
        constructor() {
            this.init();
        }

        init() {
            this.setupPropertyCards();
            this.setupPropertyFilters();
            this.setupPropertySearch();
            this.setupImageGallery();
        }

        setupPropertyCards() {
            // Add hover effects and animations to property cards
            const cards = document.querySelectorAll('.property-card');
            cards.forEach(card => {
                card.addEventListener('mouseenter', this.handleCardHover.bind(this));
                card.addEventListener('mouseleave', this.handleCardLeave.bind(this));
            });
        }

        handleCardHover(e) {
            const card = e.currentTarget;
            const image = card.querySelector('.property-image');

            // Add subtle scale effect to image
            if (image) {
                image.style.transform = 'scale(1.05)';
                image.style.transition = 'transform 0.3s ease';
            }

            // Add glow effect to price
            const price = card.querySelector('.property-price');
            if (price) {
                price.style.textShadow = '0 0 10px rgba(0, 102, 204, 0.3)';
            }
        }

        handleCardLeave(e) {
            const card = e.currentTarget;
            const image = card.querySelector('.property-image');

            // Reset image scale
            if (image) {
                image.style.transform = 'scale(1)';
            }

            // Reset price glow
            const price = card.querySelector('.property-price');
            if (price) {
                price.style.textShadow = 'none';
            }
        }

        setupPropertyFilters() {
            const filterInputs = document.querySelectorAll('.property-filters input, .property-filters select');
            filterInputs.forEach(input => {
                input.addEventListener('change', this.handleFilterChange.bind(this));
            });
        }

        handleFilterChange(e) {
            // Debounce filter changes
            clearTimeout(this.filterTimeout);
            this.filterTimeout = setTimeout(() => {
                this.applyFilters();
            }, 300);
        }

        applyFilters() {
            const cards = document.querySelectorAll('.property-card');
            const filters = this.getFilterValues();

            cards.forEach(card => {
                const shouldShow = this.matchesFilters(card, filters);
                card.style.display = shouldShow ? 'block' : 'none';

                // Add fade animation
                if (shouldShow) {
                    card.style.animation = 'fadeIn 0.3s ease-in-out';
                }
            });
        }

        getFilterValues() {
            return {
                priceMin: parseInt(document.querySelector('[name="price_min"]')?.value) || 0,
                priceMax: parseInt(document.querySelector('[name="price_max"]')?.value) || Infinity,
                bedrooms: document.querySelector('[name="bedrooms"]')?.value || '',
                propertyType: document.querySelector('[name="property_type"]')?.value || '',
                location: document.querySelector('[name="location"]')?.value || ''
            };
        }

        matchesFilters(card, filters) {
            const price = parseInt(card.dataset.price) || 0;
            const bedrooms = card.dataset.bedrooms || '';
            const propertyType = card.dataset.type || '';
            const location = card.dataset.location || '';

            return price >= filters.priceMin &&
                   price <= filters.priceMax &&
                   (filters.bedrooms === '' || bedrooms === filters.bedrooms) &&
                   (filters.propertyType === '' || propertyType === filters.propertyType) &&
                   (filters.location === '' || location.toLowerCase().includes(filters.location.toLowerCase()));
        }

        setupPropertySearch() {
            const searchInput = document.querySelector('.property-search-input');
            if (searchInput) {
                searchInput.addEventListener('input', this.handleSearch.bind(this));
            }
        }

        handleSearch(e) {
            const query = e.target.value.toLowerCase();
            const cards = document.querySelectorAll('.property-card');

            cards.forEach(card => {
                const title = card.querySelector('.property-title')?.textContent.toLowerCase() || '';
                const address = card.querySelector('.property-address')?.textContent.toLowerCase() || '';
                const shouldShow = title.includes(query) || address.includes(query);

                card.style.display = shouldShow ? 'block' : 'none';

                if (shouldShow) {
                    card.style.animation = 'fadeIn 0.3s ease-in-out';
                }
            });
        }

        setupImageGallery() {
            const galleries = document.querySelectorAll('.property-gallery');
            galleries.forEach(gallery => {
                const images = gallery.querySelectorAll('img');
                images.forEach((img, index) => {
                    if (index > 0) { // Skip main image
                        img.addEventListener('click', () => this.openImageModal(img.src));
                    }
                });
            });
        }

        openImageModal(src) {
            // Create modal for image viewing
            const modal = document.createElement('div');
            modal.className = 'modal property-image-modal';
            modal.innerHTML = `
                <div class="modal-content">
                    <span class="modal-close">&times;</span>
                    <img src="${src}" alt="Property Image" style="max-width: 100%; max-height: 80vh;">
                </div>
            `;

            document.body.appendChild(modal);

            // Add close functionality
            const closeBtn = modal.querySelector('.modal-close');
            closeBtn.addEventListener('click', () => modal.remove());

            modal.addEventListener('click', (e) => {
                if (e.target === modal) modal.remove();
            });

            // Show modal with animation
            setTimeout(() => modal.classList.add('show'), 10);
        }
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => new PropertyComponents());
    } else {
        new PropertyComponents();
    }

})();