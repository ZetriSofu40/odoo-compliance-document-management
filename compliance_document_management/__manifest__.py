{
    "name": "Compliance Documents",
    "version": "17.0.1.0.1",
    "summary": "Centralized compliance documents, expiry reminders, renewals and audit history",
    "description": (
        "Compliance Documents provides a company-wide "
        "register for licenses, permits, insurance policies, certificates, "
        "identity documents, and other time-sensitive compliance evidence. "
        "It includes configurable reminder policies, activities, email "
        "notifications, renewal chains, dashboards, multi-company controls, "
        "and immutable reminder history."
    ),
    "category": "Productivity/Documents",
    "author": "Kyaw Thurein Thaung",
    "maintainer": "Kyaw Thurein Thaung",
    "support": "kyawthureinthaung40@outlook.com",
    "website": "https://github.com/ZetriSofu40/odoo-compliance-document-management",
    "license": "OPL-1",
    "images": ["static/description/screenshots/02-compliance-dashboard.png"],
    "depends": ["base", "mail", "contacts"],
    "data": [
        "security/compliance_security.xml",
        "security/ir.model.access.csv",
        "data/compliance_sequence.xml",
        "data/compliance_mail_template.xml",
        "data/compliance_document_type_data.xml",
        "data/compliance_cron.xml",
        "views/compliance_document_type_views.xml",
        "views/compliance_document_views.xml",
        "views/res_partner_views.xml",
        "views/compliance_menus.xml",
    ],
    "demo": ["demo/compliance_document_demo.xml"],
    "installable": True,
    "application": True,
    "auto_install": False,
}
