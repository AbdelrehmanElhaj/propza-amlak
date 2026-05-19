from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ─── Saudi Identity ──────────────────────────────────────────
    sa_id_type = fields.Selection([
        ('national_id', 'هوية وطنية'),
        ('iqama',       'إقامة'),
        ('gcc',         'هوية خليجي'),
        ('passport',    'جواز سفر'),
        ('company',     'سجل تجاري'),
    ], string='نوع الهوية')

    sa_national_id = fields.Char(
        string='رقم الهوية / الإقامة',
        help='National ID (10 digits) or Iqama number'
    )
    sa_id_expiry = fields.Date(string='تاريخ انتهاء الهوية')
    sa_id_verified = fields.Boolean(
        string='هوية محققة',
        default=False,
        help='Verified through National Information Center'
    )

    # ─── Commercial Registration ─────────────────────────────────
    sa_cr_number = fields.Char(string='رقم السجل التجاري')
    sa_cr_expiry = fields.Date(string='تاريخ انتهاء السجل التجاري')

    # NOTE: Role flags (is_property_owner / is_tenant / is_broker /
    # broker_license) moved to sa_property_base since the base property and
    # tenancy models reference them in domains.

    # ─── IBAN for rent collection ────────────────────────────────
    sa_iban = fields.Char(
        string='رقم IBAN',
        help='Saudi IBAN (SA + 22 digits)'
    )

    @api.constrains('sa_national_id', 'sa_id_type')
    def _check_national_id(self):
        for rec in self:
            if rec.sa_national_id and rec.sa_id_type == 'national_id':
                nid = rec.sa_national_id.strip()
                if not nid.isdigit() or len(nid) != 10:
                    raise ValidationError(
                        _('رقم الهوية الوطنية يجب أن يكون 10 أرقام')
                    )
                if not nid.startswith('1') and not nid.startswith('2'):
                    raise ValidationError(
                        _('رقم الهوية الوطنية يبدأ بـ 1 (مواطن) أو 2 (مقيم)')
                    )

    @api.constrains('sa_iban')
    def _check_iban(self):
        for rec in self:
            if rec.sa_iban:
                iban = rec.sa_iban.replace(' ', '').upper()
                if not iban.startswith('SA') or len(iban) != 24:
                    raise ValidationError(
                        _('رقم IBAN السعودي يجب أن يبدأ بـ SA ويكون 24 حرفاً')
                    )
