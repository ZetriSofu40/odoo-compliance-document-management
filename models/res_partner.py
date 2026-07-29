from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    compliance_document_ids = fields.One2many(
        "compliance.document",
        "partner_id",
        string="Compliance Documents",
        groups="compliance_document_management.group_compliance_reader",
    )
    compliance_document_count = fields.Integer(
        compute="_compute_compliance_document_count",
        groups="compliance_document_management.group_compliance_reader",
    )

    def _compute_compliance_document_count(self):
        grouped = self.env["compliance.document"]._read_group(
            [("partner_id", "in", self.ids)],
            ["partner_id"],
            ["__count"],
        )
        counts = {partner.id: count for partner, count in grouped}
        for partner in self:
            partner.compliance_document_count = counts.get(partner.id, 0)

    def action_view_compliance_documents(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "compliance_document_management.action_compliance_document"
        )
        action["domain"] = [("partner_id", "=", self.id)]
        action["context"] = {
            "default_holder_type": "partner",
            "default_partner_id": self.id,
        }
        return action

