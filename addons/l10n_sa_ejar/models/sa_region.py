from odoo import models, fields, api


class SaudiRegion(models.Model):
    _name = 'sa.region'
    _description = 'Saudi Administrative Region'
    _order = 'name'

    name = fields.Char(string='Region Name (EN)', required=True)
    name_ar = fields.Char(string='اسم المنطقة', required=True)
    code = fields.Char(string='Region Code', required=True)
    capital = fields.Char(string='Capital City')
    capital_ar = fields.Char(string='عاصمة المنطقة')
    active = fields.Boolean(default=True)

    # Cities within region
    city_ids = fields.One2many(
        'sa.city', 'region_id', string='Cities'
    )
    city_count = fields.Integer(compute='_compute_city_count')

    @api.depends('city_ids')
    def _compute_city_count(self):
        for rec in self:
            rec.city_count = len(rec.city_ids)

    def name_get(self):
        result = []
        for rec in self:
            name = f"{rec.name_ar} ({rec.name})" if rec.name_ar else rec.name
            result.append((rec.id, name))
        return result


class SaudiCity(models.Model):
    _name = 'sa.city'
    _description = 'Saudi City'
    _order = 'name_ar'

    name = fields.Char(string='City Name (EN)', required=True)
    name_ar = fields.Char(string='اسم المدينة', required=True)
    region_id = fields.Many2one('sa.region', string='Region', required=True, ondelete='cascade')

    # Riyadh rent freeze flag (Sep 2025 regulation)
    rent_freeze = fields.Boolean(
        string='Rent Freeze Active',
        help='Riyadh: No rent increase allowed for 5 years from Sep 2025'
    )

    def name_get(self):
        result = []
        for rec in self:
            name = rec.name_ar or rec.name
            result.append((rec.id, name))
        return result
