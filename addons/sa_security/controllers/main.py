# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class PmsSecurityController(http.Controller):

    @http.route('/pms/role-matrix', type='http', auth='user', website=False)
    def role_matrix(self, **kwargs):
        """يعرض مصفوفة الصلاحيات كصفحة HTML داخل النظام.
        مفتوح للمستخدمين المسجلين فقط (auth='user').
        """
        return request.render('sa_security.role_matrix_template_view', {})
