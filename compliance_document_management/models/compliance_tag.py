from odoo import fields, models


class ComplianceDocumentTag(models.Model):
    _name = "compliance.document.tag"
    _description = "Compliance Document Tag"
    _order = "name"
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    color = fields.Integer()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        index=True,
        help="Leave empty to make this tag available to every company.",
    )

    _sql_constraints = [
        (
            "name_company_unique",
            "UNIQUE(name, company_id)",
            "A compliance tag with this name already exists for the company.",
        ),
    ]
