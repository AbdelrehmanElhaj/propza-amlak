# -*- coding: utf-8 -*-
"""Role flags on res.partner that the property/tenancy models depend on.

These live in the base because property.tenancy.partner_id and related
domains reference them. Saudi-identity fields (national ID, IBAN, etc.)
stay in l10n_sa_ejar — they're separate concerns.
"""
from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_property_owner = fields.Boolean(string='مالك عقار')
    is_tenant = fields.Boolean(string='مستأجر')
    is_broker = fields.Boolean(string='وسيط عقاري')
    broker_license = fields.Char(string='رقم ترخيص الوساطة')
