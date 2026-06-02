# -*- coding: utf-8 -*-
import math
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaCrmLeadMatch(models.Model):
    _inherit = 'sa.crm.lead'

    recommended_property_ids = fields.Many2many(
        'property.property',
        'sa_crm_lead_property_rel',
        'lead_id', 'property_id',
        string='العقارات المقترحة',
    )
    recommended_count = fields.Integer(
        string='عدد المقترحات',
        compute='_compute_recommended_count',
    )
    recommendation_note = fields.Text(string='ملاحظات التوصية')

    @api.depends('recommended_property_ids')
    def _compute_recommended_count(self):
        for rec in self:
            rec.recommended_count = len(rec.recommended_property_ids)

    def action_recommend_properties(self):
        self.ensure_one()
        properties = self.env['property.property'].search(self._build_matching_domain())
        if not properties:
            self.recommended_property_ids = [(5, 0, 0)]
            self.recommendation_note = _(
                'لم يتم العثور على عقارات مطابقة حالياً. حاول تعديل تفضيلات العميل.'
            )
            return {
                'type': 'ir.actions.act_window',
                'name': _('العقارات المطابقة'),
                'res_model': 'property.property',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', [])],
            }

        scored = sorted(
            properties,
            key=lambda prop: self._score_property(prop),
            reverse=True,
        )
        selected = scored[:8]
        selected_ids = [prop.id for prop in selected]
        self.recommended_property_ids = [(6, 0, selected_ids)]
        self.recommendation_note = _(
            'تم اختيار أفضل %(count)s عقاراً مطابقة لتفضيلات العميل.') % {
            'count': len(selected)
        }
        return {
            'type': 'ir.actions.act_window',
            'name': _('العقارات المقترحة'),
            'res_model': 'property.property',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', selected_ids)],
        }

    def _score_property(self, property_rec):
        score = 0.0
        if self.property_type and property_rec.property_type == self.property_type:
            score += 20.0
        if self.preferred_region_id and property_rec.sa_region_id == self.preferred_region_id:
            score += 20.0

        if self.rooms_min and property_rec.sa_rooms:
            score += min(10.0, max(0.0, 10.0 - abs(property_rec.sa_rooms - self.rooms_min)))
        if self.bathrooms_min and property_rec.sa_bathrooms:
            score += min(10.0, max(0.0, 10.0 - abs(property_rec.sa_bathrooms - self.bathrooms_min)))

        if self.area_min_sqm and property_rec.sa_area_sqm:
            score += min(10.0, max(0.0, 10.0 - abs(property_rec.sa_area_sqm - self.area_min_sqm) / max(1.0, self.area_min_sqm) * 10.0))
        if self.area_max_sqm and property_rec.sa_area_sqm:
            if property_rec.sa_area_sqm <= self.area_max_sqm:
                score += 5.0

        if self.budget_max and property_rec.rent_amount is not None:
            if self.lead_type == 'rent':
                score += max(0.0, 10.0 - abs(property_rec.rent_amount - self.budget_max) / max(1.0, self.budget_max) * 10.0)
            elif self.lead_type == 'buy':
                score += max(0.0, 10.0 - abs((property_rec.price_amount or 0.0) - self.budget_max) / max(1.0, self.budget_max) * 10.0)

        if self.furnished_pref and self.furnished_pref != 'any':
            if property_rec.sa_furnished == self.furnished_pref:
                score += 5.0

        preferences = [
            ('parking_required', 'sa_parking', True, 5.0),
            ('pool_required', 'sa_pool', True, 5.0),
            ('garden_required', 'sa_garden', True, 5.0),
            ('elevator_required', 'sa_elevator', True, 5.0),
        ]
        for field_name, prop_field, expected, weight in preferences:
            if getattr(self, field_name) and getattr(property_rec, prop_field) == expected:
                score += weight

        return int(math.ceil(score))
