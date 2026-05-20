from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class EjarSyncLog(models.Model):
    """
    Immutable audit record for every Ejar API interaction.

    Created for each outbound call (and inbound webhook/poll).
    Never updated after creation — append-only audit trail.
    """

    _name = 'ejar.sync.log'
    _description = 'سجل مزامنة إيجار'
    _order = 'create_date desc, id desc'
    _rec_name = 'display_name'

    # ── Company isolation ─────────────────────────────────────────────
    company_id = fields.Many2one(
        'res.company',
        string='الشركة',
        required=True,
        default=lambda self: self.env.company,
        ondelete='cascade',
        index=True,
    )

    # ── Related contract ──────────────────────────────────────────────
    contract_id = fields.Many2one(
        'ejar.contract',
        string='العقد',
        ondelete='set null',
        index=True,
    )
    contract_ref = fields.Char(
        related='contract_id.name',
        string='رقم العقد',
        store=True,
        readonly=True,
    )

    # ── Operation metadata ────────────────────────────────────────────
    action = fields.Char(
        string='الإجراء',
        required=True,
        help='e.g. create_contract, add_party, submit_contract, poll_status',
    )
    direction = fields.Selection([
        ('outbound', 'صادر → إيجار'),
        ('inbound',  'وارد ← إيجار'),
    ], string='الاتجاه', required=True, default='outbound')

    http_method = fields.Char(string='طريقة HTTP', size=10)
    endpoint = fields.Char(string='المسار')
    http_status = fields.Integer(string='رمز HTTP')

    # ── Tracking ──────────────────────────────────────────────────────
    correlation_id = fields.Char(
        string='معرّف الارتباط',
        index=True,
        help='UUID4 propagated through all log lines for this request',
    )
    idempotency_key = fields.Char(string='مفتاح التكامل')
    attempt = fields.Integer(string='المحاولة', default=1)
    duration_ms = fields.Integer(string='المدة (مللي ثانية)')

    # ── Result ────────────────────────────────────────────────────────
    status = fields.Selection([
        ('success', 'نجاح'),
        ('error',   'خطأ'),
        ('retry',   'إعادة المحاولة'),
        ('skipped', 'تم التخطي (مكتمل مسبقاً)'),
    ], string='النتيجة', required=True, default='success')

    error_type = fields.Char(
        string='نوع الخطأ',
        help='Exception class name (e.g. EjarValidationError)',
    )
    error_message = fields.Text(string='رسالة الخطأ')
    is_permanent_error = fields.Boolean(
        string='خطأ دائم',
        default=False,
        help='True = dead-letter; False = eligible for retry',
    )

    # ── Payload (sanitized — never contains api_key, iban, national_id) ──
    request_body = fields.Text(string='جسم الطلب (JSON)')
    response_body = fields.Text(string='جسم الاستجابة (JSON)')

    # ── Display ───────────────────────────────────────────────────────
    display_name = fields.Char(
        compute='_compute_display_name',
        store=True,
    )

    @api.depends('action', 'status', 'create_date')
    def _compute_display_name(self):
        status_labels = dict(self._fields['status'].selection)
        for rec in self:
            date_str = rec.create_date.strftime('%Y-%m-%d %H:%M') if rec.create_date else ''
            status = status_labels.get(rec.status, '')
            rec.display_name = f"[{status}] {rec.action or ''} — {date_str}"

    # ── Prevent updates (append-only) ─────────────────────────────────

    def write(self, vals):
        # Allow only specific system fields that Odoo may touch
        safe = {'active'}
        if not (set(vals.keys()) <= safe):
            _logger.warning(
                "Attempt to mutate ejar.sync.log records %s — ignored",
                self.ids,
            )
            return True
        return super().write(vals)

    # ── Factory ───────────────────────────────────────────────────────

    @api.model
    def log_call(
        self,
        *,
        action: str,
        contract_id: int | None = None,
        company_id: int | None = None,
        direction: str = 'outbound',
        http_method: str = '',
        endpoint: str = '',
        http_status: int = 0,
        correlation_id: str = '',
        idempotency_key: str = '',
        attempt: int = 1,
        duration_ms: int = 0,
        status: str = 'success',
        error_type: str = '',
        error_message: str = '',
        is_permanent_error: bool = False,
        request_body: str = '',
        response_body: str = '',
    ) -> 'EjarSyncLog':
        """
        Convenience factory that creates a log record with sudo().

        Uses sudo() because sync logs must be written even when the
        initiating user has restricted permissions.
        """
        return self.sudo().create({
            'action': action,
            'contract_id': contract_id,
            'company_id': company_id or self.env.company.id,
            'direction': direction,
            'http_method': http_method,
            'endpoint': endpoint,
            'http_status': http_status,
            'correlation_id': correlation_id,
            'idempotency_key': idempotency_key,
            'attempt': attempt,
            'duration_ms': duration_ms,
            'status': status,
            'error_type': error_type,
            'error_message': error_message,
            'is_permanent_error': is_permanent_error,
            'request_body': request_body[:65536] if request_body else '',
            'response_body': response_body[:65536] if response_body else '',
        })
