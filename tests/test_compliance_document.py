from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestComplianceDocument(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env["res.partner"].create(
            {"name": "Compliance Test Holder", "is_company": True}
        )
        cls.document_type = cls.env["compliance.document.type"].create(
            {
                "name": "Test License",
                "code": "TEST-LIC",
                "company_id": cls.company.id,
                "warning_days": 30,
                "require_document_number": True,
                "require_issue_date": True,
                "require_attachment": False,
            }
        )
        cls.rule_30, cls.rule_7, cls.rule_0 = cls.env[
            "compliance.document.reminder.rule"
        ].create(
            [
                {
                    "document_type_id": cls.document_type.id,
                    "days_before": 30,
                    "summary": "30-day test reminder",
                    "send_email": False,
                },
                {
                    "document_type_id": cls.document_type.id,
                    "days_before": 7,
                    "summary": "7-day test reminder",
                    "send_email": False,
                },
                {
                    "document_type_id": cls.document_type.id,
                    "days_before": 0,
                    "summary": "Expiry-day test reminder",
                    "send_email": False,
                },
            ]
        )

    def _create_document(self, **extra_vals):
        today = fields.Date.today()
        vals = {
            "name": "Test Compliance Document",
            "company_id": self.company.id,
            "document_type_id": self.document_type.id,
            "partner_id": self.partner.id,
            "document_number": "DOC-TEST-001",
            "issue_date": today - timedelta(days=100),
            "expiry_date": today + timedelta(days=100),
            "responsible_user_id": self.env.user.id,
        }
        vals.update(extra_vals)
        return self.env["compliance.document"].create(vals)

    def test_activation_and_status_lifecycle(self):
        document = self._create_document(expiry_date=fields.Date.today() + timedelta(days=20))
        self.assertEqual(document.compliance_state, "due_soon")
        document.action_activate()
        self.assertEqual(document.workflow_state, "active")

        document.expiry_date = fields.Date.today() - timedelta(days=1)
        self.assertEqual(document.compliance_state, "expired")

    def test_activation_requires_configured_fields(self):
        document = self._create_document(document_number=False)
        with self.assertRaises(UserError):
            document.action_activate()

    def test_date_validation(self):
        today = fields.Date.today()
        with self.assertRaises(ValidationError):
            self._create_document(
                issue_date=today,
                expiry_date=today - timedelta(days=1),
            )

    def test_reminder_window_and_idempotency(self):
        document = self._create_document(
            expiry_date=fields.Date.today() + timedelta(days=5),
            workflow_state="active",
        )
        first_logs = document._process_due_reminders(today=fields.Date.today())
        self.assertEqual(len(first_logs), 1)
        self.assertEqual(first_logs.threshold_days, 7)
        self.assertTrue(first_logs.activity_id)

        second_logs = document._process_due_reminders(today=fields.Date.today())
        self.assertFalse(second_logs)
        self.assertEqual(len(document.reminder_log_ids), 1)

    def test_reminder_does_not_backfill_every_threshold(self):
        document = self._create_document(
            expiry_date=fields.Date.today() + timedelta(days=20),
            workflow_state="active",
        )
        logs = document._process_due_reminders(today=fields.Date.today())
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs.threshold_days, 30)

    def test_renewal_preserves_history(self):
        old_document = self._create_document(workflow_state="active")
        action = old_document.action_create_renewal()
        renewal = self.env["compliance.document"].browse(action["res_id"])

        self.assertEqual(old_document.workflow_state, "renewal")
        self.assertEqual(renewal.previous_document_id, old_document)
        self.assertEqual(renewal.workflow_state, "draft")
        renewal.write(
            {
                "document_number": "DOC-TEST-002",
                "issue_date": fields.Date.today(),
                "expiry_date": fields.Date.today() + timedelta(days=365),
            }
        )
        renewal.action_activate()
        self.assertEqual(old_document.workflow_state, "superseded")
        self.assertEqual(renewal.workflow_state, "active")

    def test_operational_history_cannot_be_deleted(self):
        document = self._create_document(workflow_state="active")
        with self.assertRaises(UserError):
            document.unlink()

    def test_reader_is_read_only_and_company_isolated(self):
        other_company = self.env["res.company"].create({"name": "Other Compliance Company"})
        other_type = self.document_type.copy(
            {"name": "Other Company Type", "code": "OTHER", "company_id": other_company.id}
        )
        other_document = self.env["compliance.document"].create(
            {
                "name": "Other Company Document",
                "company_id": other_company.id,
                "document_type_id": other_type.id,
                "partner_id": self.partner.id,
                "document_number": "OTHER-001",
                "issue_date": fields.Date.today(),
                "expiry_date": fields.Date.today() + timedelta(days=365),
                "responsible_user_id": self.env.user.id,
            }
        )
        reader = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Compliance Reader",
                "login": "compliance.reader.test",
                "email": "reader@example.com",
                "company_id": self.company.id,
                "company_ids": [Command.set([self.company.id])],
                "groups_id": [
                    Command.set(
                        [
                            self.env.ref(
                                "compliance_document_management.group_compliance_reader"
                            ).id
                        ]
                    )
                ],
            }
        )
        visible_ids = self.env["compliance.document"].with_user(reader).search([]).ids
        self.assertNotIn(other_document.id, visible_ids)

        visible_document = self._create_document()
        with self.assertRaises(AccessError):
            visible_document.with_user(reader).write({"name": "Unauthorized Change"})
