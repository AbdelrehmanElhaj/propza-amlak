# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettingsEjar(models.TransientModel):
    _inherit = 'res.config.settings'

    ejar_api_gateway = fields.Selection(
        [
            ('moho', 'NHC Moho gateway (ECRS)'),
            ('ejar', 'Ejar direct API'),
        ],
        string='Ejar API gateway',
        config_parameter='ejar.api.gateway',
        default='moho',
    )
    ejar_api_url = fields.Char(
        string='API base URL',
        config_parameter='ejar.api.url',
        default='https://integration-gw.housingapps.sa/nhc/uat/v1/ejar/ecrs',
        help='Moho UAT example: https://integration-gw.housingapps.sa/nhc/uat/v1/ejar/ecrs',
    )
    ejar_api_key = fields.Char(
        string='API key',
        config_parameter='ejar.api.key',
    )
    ejar_api_secret = fields.Char(
        string='API secret',
        config_parameter='ejar.api.secret',
    )
    ejar_simulation_mode = fields.Boolean(
        string='Simulation mode (no live API calls)',
        config_parameter='ejar.api.simulation',
        default=True,
    )
