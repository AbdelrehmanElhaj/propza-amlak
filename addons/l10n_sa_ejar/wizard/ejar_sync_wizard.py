from odoo import models, fields, api, _
from odoo.exceptions import UserError


class EjarSyncWizard(models.TransientModel):
    _name = 'ejar.sync.wizard'
    _description = 'Ejar Contract Sync Wizard'

    tenancy_id = fields.Many2one('property.tenancy', string='الإيجار')
    action = fields.Selection([
        ('submit',  'إرسال عقد جديد لإيجار'),
        ('check',   'التحقق من حالة العقد'),
        ('renew',   'تجديد العقد'),
    ], string='الإجراء', required=True, default='submit')

    # For renewal
    new_end_date = fields.Date(string='تاريخ انتهاء جديد')
    new_rent = fields.Float(string='إيجار سنوي جديد')

    simulation_mode = fields.Boolean(
        string='وضع المحاكاة',
        default=True,
        readonly=True,
        help='Simulation mode active — real API credentials not set yet'
    )

    def action_execute(self):
        self.ensure_one()
        tenancy = self.tenancy_id

        if self.action == 'submit':
            if not tenancy.ejar_contract_id:
                tenancy.action_create_ejar_contract()
            return tenancy.ejar_contract_id.action_submit_to_ejar()

        elif self.action == 'check':
            if not tenancy.ejar_contract_id:
                raise UserError(_('لا يوجد عقد إيجار مرتبط'))
            tenancy.ejar_contract_id.action_check_ejar_status()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('تم التحديث'),
                    'message': _('تم تحديث حالة العقد من إيجار'),
                    'type': 'success',
                }
            }

        elif self.action == 'renew':
            if not self.new_end_date or not self.new_rent:
                raise UserError(_('يجب تحديد تاريخ انتهاء جديد وقيمة إيجار'))
            contract = tenancy.ejar_contract_id
            if not contract:
                raise UserError(_('لا يوجد عقد إيجار للتجديد'))
            api = self.env['ejar.api.connector']
            result = api.renew_contract(contract, self.new_end_date, self.new_rent)
            if result.get('success'):
                contract.write({
                    'end_date': self.new_end_date,
                    'rent_amount': self.new_rent,
                    'ejar_status': 'renewed',
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('تم التجديد'),
                        'message': _('تم تجديد العقد بنجاح'),
                        'type': 'success',
                    }
                }
