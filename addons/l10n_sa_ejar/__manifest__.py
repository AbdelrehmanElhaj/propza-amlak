{
    'name': 'Saudi Arabia - Ejar Integration',
    'name_ar': 'تكامل منصة إيجار - المملكة العربية السعودية',
    'version': '17.0.4.0.0',
    'category': 'Real Estate',
    'summary': 'Async Ejar ECRS integration with webhook callbacks and queue_job for Saudi real estate brokerage',
    'description': """
        Saudi Arabia — Ejar Platform Integration (ECRS) v4
        ====================================================
        Async contract lifecycle via OCA queue_job with webhook support:

        • No-blocking-UI submission — jobs run in background workers
        • Per-job retry with exponential backoff
          - Submission:  1 min → 5 min → 30 min → 2 hr → 4 hr (max 5 retries)
          - Polling:     5 min → 15 min → 30 min → 1 hr  (max 20 retries)
          - Documents:   30 s → 2 min → 10 min → 30 min  (max 4 retries)
        • Permanent-error dead-lettering:
          - Contract reset to 'ready', chatter message, Odoo activity created
        • Webhook callbacks from Ejar:
          - Secure HMAC-SHA256 signature validation
          - Replay attack prevention (timestamp window ±300s)
          - Idempotent processing (dedup via idempotency_key)
          - Real-time events: contract approved/rejected, acknowledgement, documents, status
        • Three dedicated queue channels:
          root.ejar.contracts  (heavy pipelines)
          root.ejar.polling    (lightweight status polls)
          root.ejar.documents  (PDF uploads)
        • Live job monitoring in contract form (state, progress, retry count)
        • Maintenance crons: cleanup stuck jobs, purge old logs/jobs
        • Multi-company SaaS with per-company brokerage identity
        • Customer company legal identity in all Ejar contracts (not Propza)
        • 9-state contract machine with state-transition guard
        • Immutable audit log for every API call (inbound & outbound)
        • Circuit breaker per company
        • Arabic-first UI with RTL support
        • Saudi regulatory compliance (RERA, NID/Iqama, IBAN, VAT)

        Worker configuration (odoo.cfg):
        ─────────────────────────────────
        [queue_job]
        channels = root:4,root.ejar:8,root.ejar.contracts:2,root.ejar.polling:10,root.ejar.documents:3

        Webhook configuration:
        ─────────────────────
        1. Generate webhook secret:  openssl rand -hex 32
        2. Configure per company:    ejar.webhook.secret.company_{id}
        3. Configure Ejar to send callbacks to: https://your-odoo.com/ejar/webhook
    """,
    'author': 'Abdelrehman Elhaj',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'sa_property_base',
        'account',
        'mail',
        'queue_job',         # OCA — async job processing
    ],
    'data': [
        # Security — must load first
        'security/ejar_security.xml',
        'security/ir.model.access.csv',
        # Reference data
        'data/sa_regions_data.xml',
        'data/ejar_sequence.xml',
        # Crons
        'data/ejar_cron.xml',
        'data/ejar_queue_cron.xml',
        # Base views
        'views/sa_region_views.xml',
        'views/property_property_views.xml',
        'views/property_tenancy_views.xml',
        'views/res_partner_views.xml',
        'views/ejar_brokerage_profile_views.xml',
        'views/res_config_settings_views.xml',
        'views/ejar_contract_views.xml',
        'views/ejar_sync_log_views.xml',
        # Wizards (must precede ejar_contract_job_views which inherits submit wizard)
        'wizard/ejar_sync_wizard_views.xml',
        'wizard/ejar_submit_wizard_views.xml',
        'wizard/ejar_upload_doc_wizard_views.xml',
        # Job monitoring overlays (inherit from contract + submit wizard views above)
        'views/ejar_contract_job_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
