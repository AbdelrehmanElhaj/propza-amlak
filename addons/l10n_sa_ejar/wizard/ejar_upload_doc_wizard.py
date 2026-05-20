from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class EjarUploadDocWizard(models.TransientModel):
    """
    Wizard to upload the signed contract PDF.

    After upload, automatically moves the contract to 'ready' if all
    other required data is present.
    """

    _name = 'ejar.upload.doc.wizard'
    _description = 'معالج رفع العقد الموقّع'

    contract_id = fields.Many2one(
        'ejar.contract',
        string='العقد',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    signed_doc = fields.Binary(
        string='العقد الموقّع (PDF)',
        required=True,
    )
    signed_doc_filename = fields.Char(string='اسم الملف')

    # Validation
    @api.constrains('signed_doc_filename')
    def _check_pdf(self):
        for rec in self:
            if rec.signed_doc_filename and not rec.signed_doc_filename.lower().endswith('.pdf'):
                raise UserError(_('يجب أن يكون الملف بصيغة PDF'))

    def action_upload(self):
        self.ensure_one()
        if not self.signed_doc:
            raise UserError(_('يرجى اختيار ملف PDF للرفع'))

        contract = self.contract_id
        contract.write({
            'signed_doc': self.signed_doc,
            'signed_doc_filename': self.signed_doc_filename or f'{contract.name}.pdf',
        })

        contract.message_post(
            body=_('تم رفع العقد الموقّع: %s')
            % (self.signed_doc_filename or 'contract.pdf'),
        )

        # Auto-advance to 'ready' if all data is present
        if contract.ejar_status == 'building' and contract.is_ready_to_submit:
            contract._set_status('ready')
            contract.message_post(body=_('اكتملت بيانات العقد — جاهز للإرسال'))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('تم الرفع'),
                'message': _('تم رفع العقد الموقّع بنجاح'),
                'type': 'success',
                'sticky': False,
            },
        }
