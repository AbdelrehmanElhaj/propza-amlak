# Propza Modern Theme Module

## Overview

A comprehensive modern web application theme for Odoo 17 featuring professional UI/UX design with Saudi Arabian branding. The theme is fully responsive, supports dark mode, and includes animations and interactive components.

## Features

### 🎨 Design System
- **Modern Color Palette**: Primary (Blue #0066CC), Secondary (Green #00A86B), Accent (Gold #FFB84D)
- **Professional Typography**: Modern sans-serif fonts with optimal readability
- **8px Grid System**: Consistent spacing and alignment
- **Subtle Shadows**: Depth and hierarchy effects
- **Rounded Corners**: Modern, friendly aesthetic

### 🏠 Property Management Components
- **Property Cards**: Interactive cards with images, pricing, features, and status badges
- **Property Filters**: Advanced filtering by price, bedrooms, type, and location
- **Property Search**: Real-time search with instant results
- **Image Galleries**: Interactive property image galleries with modal viewing
- **Status Indicators**: Visual status badges (Available, Rented, Maintenance)
- **Property Details**: Comprehensive property detail layouts with agent info
- **Property KPIs**: Specialized dashboard cards for occupancy, vacancies, maintenance
- **Analytics Charts**: Property-specific charts and trend analysis
- **Recent Activities**: Activity feeds with property-related events
- **Quick Actions**: Fast access buttons for common property management tasks

### 📱 Responsive Design
- Mobile-first approach
- Breakpoints: 576px (SM), 768px (MD), 992px (LG), 1200px (XL), 1920px (2K)
- Adaptive layouts for all device sizes
- Touch-friendly controls (min 44px for mobile)

### 🌙 Dark Mode
- Automatic system theme detection
- Manual toggle button
- Persistent user preference (localStorage)
- Smooth transitions between themes
- High contrast support

### ✨ Animations
- Fade in/out transitions
- Slide animations (up, left, right)
- Scale and bounce effects
- Hover animations
- Loading spinners
- Smooth transitions on all interactions

### 🧩 Components
- **Buttons**: Primary, secondary, success, danger, warning, info variants + outlines
- **Forms**: Inputs, textareas, selects, checkboxes, radios with validation
- **Cards**: Standard, KPI, property showcase cards with hover effects
- **Tables**: Striped, bordered, compact, hoverable variants
- **Navigation**: Navbar, sidebar, breadcrumbs, tabs, pills, pagination
- **Modals**: Alerts, dialogs, tooltips, popovers, spinners, progress bars
- **Dashboard**: KPI cards, charts, statistics, top lists

## Installation

### 1. Extract Module
The module is located at: `/odoo17/addons/sa_theme_propza`

### 2. Install Module
```bash
# Via Odoo UI:
# 1. Go to Apps > Modules
# 2. Search for "Propza Modern Theme"
# 3. Click Install

# Via Command Line:
python manage.py shell -d demodb
from odoo import api, SUPERUSER_ID
env = api.Environment(cr, SUPERUSER_ID, {})
env['ir.module.module'].search([('name', '=', 'sa_theme_propza')]).button_install()
```

### 3. Activate Theme
After installation, the theme CSS is automatically loaded in:
- Backend: `/web/` URLs
- Frontend: Customer portals

## CSS Variables

The theme uses CSS custom properties for easy customization:

```css
:root {
    /* Primary Colors */
    --propza-primary: #0066CC;
    --propza-secondary: #00A86B;
    --propza-accent: #FFB84D;
    
    /* Status Colors */
    --propza-success: #10B981;
    --propza-warning: #F59E0B;
    --propza-danger: #EF4444;
    
    /* Spacing (8px grid) */
    --propza-space-1: 0.25rem;  /* 4px */
    --propza-space-2: 0.5rem;   /* 8px */
    --propza-space-4: 1rem;     /* 16px */
    --propza-space-6: 1.5rem;   /* 24px */
    
    /* Border Radius */
    --propza-radius-md: 0.5rem;
    --propza-radius-lg: 0.75rem;
    --propza-radius-xl: 1rem;
}
```

## CSS Files

### Static Assets Structure
```
sa_theme_propza/
├── static/src/
│   ├── css/
│   │   ├── variables.css          # CSS variables & theming
│   │   ├── base.css               # Global styles, typography
│   │   ├── layout.css             # Grid, flexbox, spacing
│   │   ├── buttons.css            # Button styles & variants
│   │   ├── forms.css              # Form controls, inputs
│   │   ├── cards.css              # Card components
│   │   ├── navigation.css         # Navigation components
│   │   ├── dashboard.css          # Dashboard-specific styles
│   │   ├── tables.css             # Table styles & variants
│   │   ├── modals.css             # Modals, alerts, popovers
│   │   ├── animations.css         # Keyframe animations
│   │   ├── responsive.css         # Media queries
│   │   └── dark_mode.css          # Dark mode overrides
│   ├── js/
│   │   ├── theme.js               # Main theme initialization
│   │   ├── theme_toggle.js        # Dark mode toggle logic
│   │   └── animations.js          # Animation utilities
│   └── images/                    # Theme images/assets
```

## Usage Examples

### KPI Card
```html
<div class="card card-kpi">
    <div class="kpi-content">
        <div class="kpi-icon">📊</div>
        <div class="kpi-label">Total Revenue</div>
        <div class="kpi-value">$125,430</div>
        <span class="kpi-change positive">12.5%</span>
    </div>
</div>
```

### Button Variants
```html
<!-- Primary Button -->
<button class="btn btn-primary">Save</button>

<!-- Secondary Button -->
<button class="btn btn-secondary">Cancel</button>

<!-- Danger Button -->
<button class="btn btn-danger">Delete</button>

<!-- Outline Button -->
<button class="btn btn-outline">Learn More</button>
```

### Data Table
```html
<div class="datatable">
    <div class="datatable-header">
        <div class="datatable-search">
            <input type="text" placeholder="Search..."/>
        </div>
    </div>
    <table class="table table-striped table-hover">
        <!-- Table content -->
    </table>
    <div class="datatable-footer">
        <ul class="pagination">
            <!-- Pagination -->
        </ul>
    </div>
</div>
```

### Modal Dialog
```html
<div class="modal show">
    <div class="modal-dialog">
        <div class="modal-header">
            <h5 class="modal-title">Confirm Action</h5>
            <button class="modal-close"></button>
        </div>
        <div class="modal-body">
            Are you sure?
        </div>
        <div class="modal-footer">
            <button class="btn btn-secondary">Cancel</button>
            <button class="btn btn-primary">Confirm</button>
        </div>
    </div>
</div>
```

## JavaScript API

### Theme Toggle
```javascript
// Toggle dark mode
window.PropsaTheme.toggle();

// Check current theme
const theme = window.PropsaTheme.getCurrentTheme(); // 'dark' or 'light'

// Programmatically set theme
window.PropsaTheme.enableDarkMode();
window.PropsaTheme.disableDarkMode();
```

### Animations
```javascript
// Fade in animation
AnimationManager.fadeIn(element, 300);

// Slide in animation
AnimationManager.slideIn(element, 'left', 300);

// Scale animation
AnimationManager.scaleIn(element, 300);

// Pulse animation
AnimationManager.pulse(element);

// Bounce animation
AnimationManager.bounce(element, 3);

// Shake animation
AnimationManager.shake(element, 500);
```

## Customization

### Change Primary Color
Edit `variables.css`:
```css
:root {
    --propza-primary: #YOUR_COLOR;
    --propza-primary-light: #YOUR_COLOR_LIGHT;
    --propza-primary-dark: #YOUR_COLOR_DARK;
}
```

### Modify Spacing Scale
Edit the spacing variables in `variables.css`:
```css
:root {
    --propza-space-4: 1.2rem; /* Change from 1rem */
    --propza-space-6: 1.8rem; /* Change from 1.5rem */
}
```

### Override Theme in Child Module
Create a CSS file in your custom module:
```css
:root {
    --propza-primary: #YOUR_COLOR;
}

body {
    /* Your custom styles */
}
```

Then declare it in your module's `__manifest__.py`:
```python
'assets': {
    'web.assets_backend': [
        'your_module/static/src/css/theme_override.css',
    ],
}
```

## Browser Support

- Chrome/Chromium (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)
- Mobile browsers (iOS Safari, Chrome Mobile)

## Performance

- **CSS**: ~25KB (minified)
- **JavaScript**: ~8KB (minified)
- **Total**: ~33KB overhead
- All animations use CSS3 for optimal performance
- Lazy-loading support for animations
- System theme detection without polling

## Accessibility

- WCAG 2.1 Level AA compliant
- Semantic HTML structure
- ARIA labels and roles
- Keyboard navigation support
- Focus indicators
- High contrast dark mode option
- Reduced motion support (`prefers-reduced-motion`)

## Dark Mode Features

### Automatic Detection
- System preference detection (`prefers-color-scheme`)
- User preference storage
- Manual toggle button

### Dark Mode Colors
- Background: #1F2937 (primary), #111827 (secondary)
- Text: #F9FAFB (primary), #D1D5DB (secondary)
- Inverted accent colors
- Adjusted shadows for depth

## Integration with Propza Modules

The theme is designed to work seamlessly with:
- `sa_dashboard` - Dashboard with KPI cards
- `sa_portal` - Customer portal interface
- `sa_property` - Property listings
- `sa_rental_cycle` - Rental management views
- `sa_maintenance` - Maintenance request tracking

## Troubleshooting

### Dark Mode Not Working
1. Clear browser cache
2. Check localStorage: `localStorage.getItem('propza-theme-mode')`
3. Verify theme.js is loaded in browser DevTools

### Styles Not Applying
1. Ensure module is installed and activated
2. Clear Odoo cache: `rm -rf ~/.local/share/Odoo/*/sessions/*`
3. Rebuild assets: `python manage.py assets build`

### Animations Too Slow
Check `prefers-reduced-motion` setting in browser or OS

## Future Enhancements

- [ ] Theme customization UI
- [ ] Additional color palettes
- [ ] Custom font support
- [ ] CSS-in-JS theme engine
- [ ] Figma design tokens export
- [ ] Theme preview mode
- [ ] A/B testing capabilities

## License

LGPL-3 - See module `__manifest__.py` for details

## Author

**Abdelrehman Elhaj**  
Website: https://propza.sa  
Email: contact@propza.sa

## Support

For issues, feature requests, or questions:
1. Check this documentation
2. Review CSS variables
3. Check browser console for errors
4. Submit issue with reproduction steps

---

**Version**: 17.0.1.0.0  
**Created**: 2024  
**Last Updated**: May 2026
