from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ComplianceDocumentType(models.Model):
    _name = "compliance.document.type"
    _description = "Compliance Document Type"
    _order = "sequence, name"
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        index=True,
        help="Leave empty to make this document type available to every company.",
    )
    validity_mode = fields.Selection(
        [("expiring", "Has Expiry Date"), ("permanent", "No Expiry Date")],
        required=True,
        default="expiring",
    )
    warning_days = fields.Integer(
        string="Expiring Soon Threshold",
        default=30,
        help="Documents enter the Expiring Soon status this many days before expiry.",
    )
    default_validity_days = fields.Integer(
        string="Default Validity (Days)",
        help="When set, the expiry date is proposed from the issue date.",
    )
    require_document_number = fields.Boolean(default=True)
    require_issue_date = fields.Boolean(default=True)
    require_attachment = fields.Boolean(
        help="Require an official file before the document can be activated."
    )
    default_responsible_user_id = fields.Many2one(
        "res.users",
        string="Default Responsible",
        domain="[(\"share\", \"=\", False)]",
        check_company=True,
    )
    escalation_user_id = fields.Many2one(
        "res.users",
        string="Escalation User",
        domain="[(\"share\", \"=\", False)]",
        check_company=True,
        help="Fallback recipient for reminder rules assigned to the escalation user.",
    )
    description = fields.Text(translate=True)
    reminder_rule_ids = fields.One2many(
        "compliance.document.reminder.rule",
        "document_type_id",
        string="Reminder Policy",
        copy=True,
    )
    document_count = fields.Integer(compute="_compute_document_count")

    _sql_constraints = [
        (
            "warning_days_nonnegative",
            "CHECK(warning_days >= 0)",
            "The expiring-soon threshold cannot be negative.",
        ),
        (
            "default_validity_nonnegative",
            "CHECK(default_validity_days >= 0)",
            "The default validity cannot be negative.",
        ),
    ]

    @api.depends("name", "code")
    def _compute_display_name(self):
        for document_type in self:
            document_type.display_name = (
                f"[{document_type.code}] {document_type.name}"
                if document_type.code
                else document_type.name
            )

    @api.depends_context("company")
    def _compute_document_count(self):
        grouped = self.env["compliance.document"].read_group(
            [("document_type_id", "in", self.ids)],
            ["document_type_id"],
            ["document_type_id"],
        )
        counts = {
            group["document_type_id"][0]: group["document_type_id_count"]
            for group in grouped
            if group["document_type_id"]
        }
        for document_type in self:
            document_type.document_count = counts.get(document_type.id, 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code"):
                vals["code"] = vals["code"].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("code"):
            vals["code"] = vals["code"].strip().upper()
        result = super().write(vals)
        if "warning_days" in vals or "validity_mode" in vals:
            documents = self.env["compliance.document"].search(
                [("document_type_id", "in", self.ids)]
            )
            documents._compute_compliance_state()
        return result

    @api.constrains("code", "company_id")
    def _check_unique_code(self):
        for document_type in self:
            duplicate = self.search_count(
                [
                    ("id", "!=", document_type.id),
                    ("code", "=", document_type.code),
                    ("company_id", "=", document_type.company_id.id or False),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _("Document type code must be unique within a company.")
                )

    def action_view_documents(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "compliance_document_management.action_compliance_document"
        )
        action["domain"] = [("document_type_id", "=", self.id)]
        action["context"] = {
            "default_document_type_id": self.id,
            "default_company_id": self.company_id.id or self.env.company.id,
        }
        return action


class ComplianceDocumentReminderRule(models.Model):
    _name = "compliance.document.reminder.rule"
    _description = "Compliance Document Reminder Rule"
    _order = "document_type_id, days_before desc, id"
    _check_company_auto = True

    document_type_id = fields.Many2one(
        "compliance.document.type",
        required=True,
        ondelete="cascade",
        index=True,
        check_company=True,
    )
    company_id = fields.Many2one(
        related="document_type_id.company_id",
        store=True,
        index=True,
    )
    active = fields.Boolean(default=True)
    days_before = fields.Integer(
        required=True,
        default=30,
        help="Create the reminder when the document enters this threshold window.",
    )
    summary = fields.Char(
        required=True,
        default="Compliance document requires attention",
        translate=True,
    )
    activity_type_id = fields.Many2one(
        "mail.activity.type",
        string="Activity Type",
        default=lambda self: self.env.ref("mail.mail_activity_data_todo"),
        required=True,
    )
    recipient_mode = fields.Selection(
        [
            ("responsible", "Document Responsible"),
            ("escalation", "Type Escalation User"),
            ("specific", "Specific User"),
        ],
        required=True,
        default="responsible",
    )
    specific_user_id = fields.Many2one(
        "res.users",
        string="Specific User",
        domain="[(\"share\", \"=\", False)]",
        check_company=True,
    )
    create_activity = fields.Boolean(default=True)
    send_email = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "days_before_nonnegative",
            "CHECK(days_before >= 0)",
            "Reminder days cannot be negative.",
        ),
        (
            "type_threshold_unique",
            "UNIQUE(document_type_id, days_before)",
            "Only one reminder rule is allowed for each threshold.",
        ),
    ]

    @api.constrains("create_activity", "send_email")
    def _check_delivery_channel(self):
        if any(not rule.create_activity and not rule.send_email for rule in self):
            raise ValidationError(
                _("Enable at least one delivery channel for every reminder rule.")
            )

    @api.constrains("recipient_mode", "specific_user_id")
    def _check_specific_recipient(self):
        if any(
            rule.recipient_mode == "specific" and not rule.specific_user_id
            for rule in self
        ):
            raise ValidationError(
                _("Select a specific user for rules using the Specific User recipient.")
            )
