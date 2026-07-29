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
        grouped = self.env["compliance.document"].read_group(
            [("partner_id", "in", self.ids)],
            ["partner_id"],
            ["partner_id"],
        )
        counts = {
            group["partner_id"][0]: group["partner_id_count"]
            for group in grouped
            if group["partner_id"]
        }
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
