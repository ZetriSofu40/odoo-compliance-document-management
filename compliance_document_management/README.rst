Compliance Documents for Odoo 18
=====================================================

Centralize licenses, permits, insurance policies, certificates, agreements,
identity records and other compliance evidence without duplicating the
specialized expiry fields already provided by Odoo applications.

Highlights
----------

* Configurable document types and evidence requirements.
* Valid, expiring-soon, expired, no-expiry and missing-date statuses.
* Multi-threshold activity and email reminders with escalation recipients.
* Idempotent daily processing and immutable reminder audit history.
* Controlled renewal workflow with superseded-document traceability.
* Contact smart buttons, expiry calendar, kanban dashboard, pivot and graph.
* Compliance Officer, Administrator and read-only Auditor access levels.
* Company-safe data separation and protected historical evidence.

Requirements
------------

* Odoo 18.0 Community or Enterprise, Odoo.sh, or self-hosted Odoo.
* Standard Odoo dependencies: Contacts and Discuss/Mail.
* Use the dedicated ``18.0`` branch. Separate version branches provide the
  supported Odoo 15.0 through 19.0 ports.

Installation
------------

* Copy ``compliance_document_management`` into an Odoo addons path.
* Restart Odoo and update the Apps list.
* Search for **Compliance Documents** and install it.
* Assign Compliance access rights to the appropriate users.
* Review document types, evidence requirements, reminder thresholds and recipients.

The optional demo package provides six sample records spanning valid,
expiring-soon, expired, permanent and incomplete scenarios.

Operational notes
-----------------

The daily scheduled action refreshes date-driven statuses and generates the
nearest due reminder threshold. Running it repeatedly does not create duplicate
activities, emails or logs for the same document, expiry date and threshold.

Historical documents with reminder or renewal evidence cannot be deleted.
Archive them when they are no longer operational.

License
-------

Odoo Proprietary License v1.0 (OPL-1). See ``LICENSE`` and ``COPYRIGHT``.
