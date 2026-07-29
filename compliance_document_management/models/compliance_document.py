import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


_logger = logging.getLogger(__name__)


class ComplianceDocument(models.Model):
    _name = "compliance.document"
    _description = "Compliance Document"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "expiry_date, reference, id"
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _("New"), tracking=True)
    reference = fields.Char(
        required=True,
        default=lambda self: _("New"),
        readonly=True,
        copy=False,
        index=True,
    )
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    document_type_id = fields.Many2one(
        "compliance.document.type",
        string="Document Type",
        required=True,
        tracking=True,
        index=True,
        check_company=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    validity_mode = fields.Selection(
        related="document_type_id.validity_mode",
        store=True,
        readonly=True,
    )
    holder_type = fields.Selection(
        [("partner", "Contact / Organization"), ("other", "Other Holder")],
        required=True,
        default="partner",
        tracking=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Document Holder",
        default=lambda self: self.env.company.partner_id,
        tracking=True,
        index=True,
    )
    holder_name = fields.Char(string="Other Holder", tracking=True)
    holder_display_name = fields.Char(
        string="Holder",
        compute="_compute_holder_display_name",
        store=True,
        index=True,
    )
    document_number = fields.Char(tracking=True, index=True)
    issuing_authority_id = fields.Many2one(
        "res.partner",
        string="Issuing Authority",
        tracking=True,
    )
    issue_date = fields.Date(tracking=True)
    expiry_date = fields.Date(tracking=True, index=True)
    days_to_expiry = fields.Integer(compute="_compute_days_to_expiry")
    responsible_user_id = fields.Many2one(
        "res.users",
        string="Responsible",
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
        index=True,
        domain="[(\"share\", \"=\", False)]",
        check_company=True,
    )
    tag_ids = fields.Many2many(
        "compliance.document.tag",
        "compliance_document_tag_rel",
        "document_id",
        "tag_id",
        string="Tags",
        check_company=True,
    )
    document_file = fields.Binary(
        string="Official Document",
        attachment=True,
        copy=False,
    )
    document_filename = fields.Char(copy=False)
    notes = fields.Html(sanitize=True)
    workflow_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("renewal", "Renewal in Progress"),
            ("superseded", "Superseded"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="draft",
        tracking=True,
        index=True,
        copy=False,
    )
    compliance_state = fields.Selection(
        [
            ("missing", "Missing Expiry Date"),
            ("permanent", "No Expiry"),
            ("valid", "Valid"),
            ("due_soon", "Expiring Soon"),
            ("expired", "Expired"),
        ],
        string="Compliance Status",
        compute="_compute_compliance_state",
        store=True,
        index=True,
    )
    previous_document_id = fields.Many2one(
        "compliance.document",
        string="Previous Document",
        copy=False,
        readonly=True,
        ondelete="restrict",
        check_company=True,
    )
    renewal_document_ids = fields.One2many(
        "compliance.document",
        "previous_document_id",
        string="Renewal Document",
        readonly=True,
    )
    renewal_count = fields.Integer(compute="_compute_renewal_count")
    reminder_log_ids = fields.One2many(
        "compliance.document.reminder.log",
        "document_id",
        string="Reminder History",
        readonly=True,
    )
    reminder_count = fields.Integer(compute="_compute_reminder_count")
    last_reminder_at = fields.Datetime(
        compute="_compute_last_reminder_at",
        store=True,
    )

    _sql_constraints = [
        (
            "reference_unique",
            "UNIQUE(reference)",
            "The compliance document reference must be unique.",
        ),
        (
            "previous_document_unique",
            "UNIQUE(previous_document_id)",
            "A compliance document can have only one direct renewal.",
        ),
    ]

    @api.depends("holder_type", "partner_id", "holder_name")
    def _compute_holder_display_name(self):
        for document in self:
            document.holder_display_name = (
                document.partner_id.display_name
                if document.holder_type == "partner"
                else document.holder_name
            )

    @api.depends("expiry_date")
    def _compute_days_to_expiry(self):
        today = fields.Date.context_today(self)
        for document in self:
            document.days_to_expiry = (
                (document.expiry_date - today).days if document.expiry_date else 0
            )

    @api.depends(
        "expiry_date",
        "document_type_id.validity_mode",
        "document_type_id.warning_days",
    )
    def _compute_compliance_state(self):
        today = fields.Date.context_today(self)
        for document in self:
            if document.validity_mode == "permanent":
                document.compliance_state = "permanent"
            elif not document.expiry_date:
                document.compliance_state = "missing"
            elif document.expiry_date < today:
                document.compliance_state = "expired"
            elif document.expiry_date <= today + timedelta(
                days=document.document_type_id.warning_days
            ):
                document.compliance_state = "due_soon"
            else:
                document.compliance_state = "valid"

    @api.depends("renewal_document_ids")
    def _compute_renewal_count(self):
        for document in self:
            document.renewal_count = len(document.renewal_document_ids)

    @api.depends("reminder_log_ids")
    def _compute_reminder_count(self):
        for document in self:
            document.reminder_count = len(document.reminder_log_ids)

    @api.depends("reminder_log_ids.sent_at")
    def _compute_last_reminder_at(self):
        for document in self:
            document.last_reminder_at = max(
                document.reminder_log_ids.mapped("sent_at"),
                default=False,
            )

    @api.onchange("holder_type")
    def _onchange_holder_type(self):
        if self.holder_type == "partner":
            self.holder_name = False
            if not self.partner_id:
                self.partner_id = self.company_id.partner_id
        else:
            self.partner_id = False

    @api.onchange("document_type_id", "issue_date")
    def _onchange_validity_dates(self):
        if not self.document_type_id:
            return
        if self.document_type_id.validity_mode == "permanent":
            self.expiry_date = False
        elif self.issue_date and self.document_type_id.default_validity_days:
            self.expiry_date = self.issue_date + timedelta(
                days=self.document_type_id.default_validity_days
            )

    @api.onchange("document_type_id")
    def _onchange_document_type_responsible(self):
        if self.document_type_id.default_responsible_user_id:
            self.responsible_user_id = self.document_type_id.default_responsible_user_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("reference") or vals.get("reference") == _("New"):
                vals["reference"] = (
                    self.env["ir.sequence"].next_by_code("compliance.document")
                    or _("New")
                )
            document_type = self.env["compliance.document.type"].browse(
                vals.get("document_type_id")
            )
            if document_type.validity_mode == "permanent":
                vals["expiry_date"] = False
            elif (
                vals.get("issue_date")
                and not vals.get("expiry_date")
                and document_type.default_validity_days
            ):
                vals["expiry_date"] = fields.Date.to_date(
                    vals["issue_date"]
                ) + timedelta(days=document_type.default_validity_days)
            if not vals.get("responsible_user_id"):
                vals["responsible_user_id"] = (
                    document_type.default_responsible_user_id.id or self.env.uid
                )
            if not vals.get("name") or vals.get("name") == _("New"):
                vals["name"] = self._prepare_default_name(vals, document_type)
        return super().create(vals_list)

    def write(self, vals):
        old_expiry_dates = {document.id: document.expiry_date for document in self}
        if vals.get("document_type_id"):
            document_type = self.env["compliance.document.type"].browse(
                vals["document_type_id"]
            )
            if document_type.validity_mode == "permanent":
                vals["expiry_date"] = False
        result = super().write(vals)
        if {"expiry_date", "document_type_id"} & set(vals):
            self._compute_compliance_state()
            self._close_obsolete_reminder_activities(old_expiry_dates)
        return result

    @api.model
    def _prepare_default_name(self, vals, document_type):
        holder_name = vals.get("holder_name")
        if vals.get("holder_type", "partner") == "partner":
            partner = self.env["res.partner"].browse(vals.get("partner_id"))
            holder_name = partner.display_name
        parts = [part for part in (document_type.name, holder_name) if part]
        return " - ".join(parts) or _("Compliance Document")

    @api.constrains("holder_type", "partner_id", "holder_name")
    def _check_document_holder(self):
        for document in self:
            if document.holder_type == "partner" and not document.partner_id:
                raise ValidationError(_("Select the contact or organization holding the document."))
            if document.holder_type == "other" and not document.holder_name:
                raise ValidationError(_("Enter the name of the document holder."))

    @api.constrains("issue_date", "expiry_date")
    def _check_document_dates(self):
        for document in self:
            if (
                document.issue_date
                and document.expiry_date
                and document.issue_date > document.expiry_date
            ):
                raise ValidationError(_("The expiry date must be on or after the issue date."))

    @api.constrains("previous_document_id", "document_type_id", "company_id")
    def _check_renewal_consistency(self):
        for document in self.filtered("previous_document_id"):
            if document.previous_document_id == document:
                raise ValidationError(_("A document cannot renew itself."))
            if document.previous_document_id.company_id != document.company_id:
                raise ValidationError(_("A renewal must belong to the same company."))
            if document.previous_document_id.document_type_id != document.document_type_id:
                raise ValidationError(_("A renewal must use the same document type."))

    def _validate_activation(self):
        for document in self:
            document_type = document.document_type_id
            missing = []
            if document_type.require_document_number and not document.document_number:
                missing.append(_("Document Number"))
            if document_type.require_issue_date and not document.issue_date:
                missing.append(_("Issue Date"))
            if document_type.require_attachment and not document.document_file:
                missing.append(_("Official Document"))
            if document_type.validity_mode == "expiring" and not document.expiry_date:
                missing.append(_("Expiry Date"))
            if missing:
                raise UserError(
                    _("Complete these required fields before activation: %s")
                    % ", ".join(missing)
                )

    def action_activate(self):
        self._validate_activation()
        self.write({"workflow_state": "active"})
        for document in self:
            document.message_post(body=_("The compliance document was activated."))
            if document.previous_document_id:
                document.previous_document_id.write({"workflow_state": "superseded"})
                document.previous_document_id.message_post(
                    body=_("This document was superseded by %s.", document.reference)
                )
        return True

    def action_start_renewal(self):
        for document in self:
            if document.validity_mode != "expiring":
                raise UserError(_("Documents without an expiry date cannot be renewed."))
            if document.workflow_state not in ("active", "renewal"):
                raise UserError(_("Only active documents can enter the renewal process."))
        self.write({"workflow_state": "renewal"})
        return True

    def action_create_renewal(self):
        self.ensure_one()
        if self.renewal_document_ids:
            renewal = self.renewal_document_ids[:1]
        else:
            self.action_start_renewal()
            renewal = self.copy(
                {
                    "name": _("%s - Renewal", self.name),
                    "reference": _("New"),
                    "workflow_state": "draft",
                    "previous_document_id": self.id,
                    "document_number": False,
                    "issue_date": False,
                    "expiry_date": False,
                    "document_file": False,
                    "document_filename": False,
                }
            )
            self.message_post(body=_("Renewal draft %s was created.", renewal.reference))
        return {
            "type": "ir.actions.act_window",
            "name": _("Document Renewal"),
            "res_model": "compliance.document",
            "view_mode": "form",
            "res_id": renewal.id,
            "target": "current",
        }

    def action_cancel(self):
        self.write({"workflow_state": "cancelled"})
        for document in self:
            document.message_post(body=_("The compliance document was cancelled."))
        return True

    def action_reset_to_draft(self):
        if not self.env.user.has_group(
            "compliance_document_management.group_compliance_manager"
        ):
            raise AccessError(_("Only Compliance Administrators can reset documents."))
        self.write({"workflow_state": "draft"})
        return True

    def action_view_renewals(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Renewal History"),
            "res_model": "compliance.document",
            "view_mode": "list,form",
            "domain": [
                "|",
                ("id", "=", self.previous_document_id.id),
                ("previous_document_id", "=", self.id),
            ],
            "context": {"create": False},
        }

    def action_view_reminder_logs(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "compliance_document_management.action_compliance_reminder_log"
        )
        action["domain"] = [("document_id", "=", self.id)]
        return action

    def action_check_reminders(self):
        if not self.env.user.has_group(
            "compliance_document_management.group_compliance_manager"
        ):
            raise AccessError(_("Only Compliance Administrators can run reminder checks."))
        self._compute_compliance_state()
        logs = self.sudo()._process_due_reminders()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Compliance Reminder Check"),
                "message": _("%s reminder(s) generated.", len(logs)),
                "type": "success",
                "sticky": False,
            },
        }

    def _close_obsolete_reminder_activities(self, old_expiry_dates):
        for document in self:
            if old_expiry_dates.get(document.id) == document.expiry_date:
                continue
            obsolete_logs = document.reminder_log_ids.filtered(
                lambda log: log.expiry_date_snapshot != document.expiry_date
                and log.activity_id
            )
            if obsolete_logs:
                obsolete_logs.mapped("activity_id").sudo().action_done(
                    feedback=_("Closed because the document expiry date changed.")
                )

    def _get_due_reminder_rule(self, today):
        self.ensure_one()
        if not self.expiry_date:
            return self.env["compliance.document.reminder.rule"]
        days_left = (self.expiry_date - today).days
        if days_left < 0:
            return self.env["compliance.document.reminder.rule"]
        rules = self.document_type_id.reminder_rule_ids.filtered("active")
        if days_left == 0:
            return rules.filtered(lambda rule: rule.days_before == 0)[:1]
        candidates = rules.filtered(
            lambda rule: rule.days_before > 0 and rule.days_before >= days_left
        ).sorted("days_before")
        return candidates[:1]

    def _get_reminder_recipient(self, rule):
        self.ensure_one()
        if rule.recipient_mode == "specific":
            recipient = rule.specific_user_id
        elif rule.recipient_mode == "escalation":
            recipient = self.document_type_id.escalation_user_id
        else:
            recipient = self.responsible_user_id
        if not recipient or not recipient.active:
            recipient = self.responsible_user_id if self.responsible_user_id.active else self.env.user
        return recipient

    def _process_due_reminders(self, today=None):
        today = fields.Date.to_date(today) if today else fields.Date.context_today(self)
        Log = self.env["compliance.document.reminder.log"]
        template = self.env.ref(
            "compliance_document_management.mail_template_compliance_expiry_reminder",
            raise_if_not_found=False,
        )
        created_logs = Log
        for document in self.filtered(
            lambda doc: doc.active
            and doc.workflow_state in ("active", "renewal")
            and doc.expiry_date
        ):
            rule = document._get_due_reminder_rule(today)
            if not rule:
                continue
            existing = Log.search_count(
                [
                    ("document_id", "=", document.id),
                    ("expiry_date_snapshot", "=", document.expiry_date),
                    ("threshold_days", "=", rule.days_before),
                ],
                limit=1,
            )
            if existing:
                continue
            recipient = document._get_reminder_recipient(rule)
            activity = self.env["mail.activity"]
            mail = self.env["mail.mail"]
            activity_created = False
            email_created = False
            if rule.create_activity:
                activity = document.activity_schedule(
                    date_deadline=document.expiry_date,
                    summary=rule.summary,
                    note=_(
                        "%(document)s (%(reference)s) expires on %(expiry)s.",
                        document=document.name,
                        reference=document.reference,
                        expiry=document.expiry_date,
                    ),
                    user_id=recipient.id,
                    activity_type_id=rule.activity_type_id.id,
                )
                activity_created = bool(activity)
            if rule.send_email and template and recipient.email:
                try:
                    with self.env.cr.savepoint():
                        mail_id = template.sudo().with_company(document.company_id).send_mail(
                            document.id,
                            force_send=False,
                            email_values={"email_to": recipient.email},
                        )
                        mail = self.env["mail.mail"].browse(mail_id)
                        email_created = bool(mail)
                except Exception:
                    _logger.exception(
                        "Unable to queue compliance reminder email for document %s",
                        document.id,
                    )
            if not activity_created and not email_created:
                activity = document.activity_schedule(
                    act_type_xmlid="mail.mail_activity_data_todo",
                    date_deadline=document.expiry_date,
                    summary=rule.summary,
                    note=_("Email delivery was unavailable; review this document manually."),
                    user_id=recipient.id,
                )
                activity_created = True
            channel = (
                "both"
                if activity_created and email_created
                else "activity"
                if activity_created
                else "email"
            )
            log = Log.create(
                {
                    "document_id": document.id,
                    "rule_id": rule.id,
                    "threshold_days": rule.days_before,
                    "expiry_date_snapshot": document.expiry_date,
                    "recipient_user_id": recipient.id,
                    "channel": channel,
                    "activity_id": activity.id,
                    "mail_id": mail.id,
                }
            )
            created_logs |= log
            document.message_post(
                body=_(
                    "Compliance reminder generated at the %(days)s-day threshold for %(user)s.",
                    days=rule.days_before,
                    user=recipient.display_name,
                )
            )
        return created_logs

    @api.model
    def _cron_process_compliance_documents(self):
        documents = self.sudo().search(
            [
                ("active", "=", True),
                ("workflow_state", "in", ("active", "renewal")),
                ("expiry_date", "!=", False),
            ]
        )
        documents._compute_compliance_state()
        documents._process_due_reminders()
        return True

    def unlink(self):
        if not self.env.user.has_group(
            "compliance_document_management.group_compliance_manager"
        ):
            raise AccessError(_("Only Compliance Administrators can delete draft records."))
        protected = self.filtered(
            lambda document: document.workflow_state not in ("draft", "cancelled")
            or document.reminder_log_ids
            or document.previous_document_id
            or document.renewal_document_ids
        )
        if protected:
            raise UserError(
                _(
                    "Documents with operational or audit history cannot be deleted. "
                    "Archive them instead."
                )
            )
        return super().unlink()


class ComplianceDocumentReminderLog(models.Model):
    _name = "compliance.document.reminder.log"
    _description = "Compliance Document Reminder Log"
    _order = "sent_at desc, id desc"
    _check_company_auto = True

    document_id = fields.Many2one(
        "compliance.document",
        required=True,
        ondelete="cascade",
        index=True,
        check_company=True,
    )
    company_id = fields.Many2one(
        related="document_id.company_id",
        store=True,
        index=True,
    )
    rule_id = fields.Many2one(
        "compliance.document.reminder.rule",
        string="Reminder Rule",
        ondelete="set null",
        check_company=True,
    )
    threshold_days = fields.Integer(required=True, readonly=True)
    expiry_date_snapshot = fields.Date(required=True, readonly=True, index=True)
    recipient_user_id = fields.Many2one(
        "res.users",
        required=True,
        readonly=True,
        check_company=True,
    )
    channel = fields.Selection(
        [("activity", "Activity"), ("email", "Email"), ("both", "Activity & Email")],
        required=True,
        readonly=True,
    )
    sent_at = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True)
    activity_id = fields.Many2one("mail.activity", readonly=True, ondelete="set null")
    mail_id = fields.Many2one("mail.mail", readonly=True, ondelete="set null")

    _sql_constraints = [
        (
            "document_threshold_unique",
            "UNIQUE(document_id, expiry_date_snapshot, threshold_days)",
            "This reminder threshold was already processed for the document expiry cycle.",
        ),
    ]

    @api.ondelete(at_uninstall=False)
    def _unlink_except_module_uninstall(self):
        raise UserError(_("Reminder audit history cannot be deleted."))
