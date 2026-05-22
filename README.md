# OpenUpgrade Scripts for Odoo Enterprise 17.0 → 18.0

Migration scripts for the Odoo Enterprise modules, written as an addition to
[OCA OpenUpgrade](https://github.com/OCA/OpenUpgrade) 18.0: OpenUpgrade migrates the community modules, this
repository the enterprise modules (and the few community modules whose 17.0 data an enterprise module leaves
behind). The scripts follow the OpenUpgrade conventions: `openupgradelib`, `@openupgrade.migrate()`, one directory
per module and version under `openupgrade_scripts_ee/`.

> These scripts need the Odoo Enterprise source code, which comes with an Odoo Enterprise subscription. This
> repository only holds migration logic.

## How it combines with OpenUpgrade 18.0

| piece | what is needed |
|---|---|
| Odoo | the 17.0 community and enterprise trees the database runs on, and the 18.0 community and enterprise trees to upgrade to |
| OCA OpenUpgrade | branch 18.0 of `OCA/OpenUpgrade`, pinned at revision `fba9d88`: its `openupgrade_framework` (server-wide module that patches Odoo for the upgrade) and `openupgrade_scripts` (community scripts) |
| openupgradelib | 3.7.3 or later, importable by the 18.0 Python (the scripts here were validated with 3.13.1) |
| this repository | `openupgrade_scripts_ee/` as the second `upgrade_path` entry |
| Python packages | the external dependencies of your installed enterprise modules, as Odoo itself requires them (for instance `xmlsec` for `l10n_nl_reports_sbr`, `phonenumbers` for `whatsapp`, `google-auth` for `social_push_notifications`, `pdf417gen` for `l10n_cl_edi`, `pyjwt` for the Indian QR bill scan) |

The 18.0 configuration used for the upgrade:

```ini
[options]
addons_path = /path/to/odoo-18.0/addons,/path/to/odoo-18.0/odoo/addons,/path/to/enterprise-18.0,/path/to/OpenUpgrade
upgrade_path = /path/to/OpenUpgrade/openupgrade_scripts/scripts,/path/to/openupgrade-enterprise/openupgrade_scripts_ee
server_wide_modules = web,openupgrade_framework
```

- `addons_path` lists the root of the OpenUpgrade checkout, the directory that contains `openupgrade_framework` and
  `openupgrade_scripts` (OpenUpgrade 18.0 has no `addons` directory).
- `upgrade_path` lists the OpenUpgrade scripts first and this repository second. Odoo runs, per module and stage, the
  version directories of every entry in ascending version order, so `base/18.0.1.0` of this repository runs before
  `base/18.0.1.3` of OpenUpgrade at each stage.
- `server_wide_modules = web,openupgrade_framework` loads the framework (the same as `--load=web,openupgrade_framework`).

**Shared library.** `openupgrade_scripts_ee/lib/` is a Python package, not a module directory. Odoo appends every
`upgrade_path` entry to `odoo.upgrade.__path__`, so whenever these scripts can run, they import it as
`from odoo.upgrade.lib import certificate` (the mechanism Odoo's own upgrade utilities use). It holds:

| module | what it does |
|---|---|
| `certificate` | creates the 18.0 `certificate.certificate` and `certificate.key` of each 17.0 certificate through the ORM (every stored compute of 18.0 runs), one savepoint per record, a mapping table `openupgrade_legacy_18_0_certificate_map` that makes a second run create nothing, and relinks the many2one fields to the new records |
| `schema` | moves the 17.0 ids of a many2one whose comodel changes into a legacy column without foreign key, so the module load does not re-add the key against ids of another table |
| `company_dependent` | converts the enterprise company-dependent fields from `ir_property` to the 18.0 jsonb columns and `ir.default`, with a marker table that makes a second run change nothing |
| `relation` | default relation table names and an ORM-shaped copy of many2many pairs into a new relation |
| `social` | per-network message and images of social posts and templates |
| `delivery` | pick-up radius of Sendcloud and FedEx carriers in the unit 18.0 computes |
| `data` | creates the records of an 18.0 data file that an update never creates (`forcecreate="0"` in a `noupdate` block) and the database lacks |
| `payroll` | keeps the salary rules, categories and input types 18.0 drops while 17.0 payslips still use them, archived and `noupdate` |

## Upgrade procedure

1. Back up the 17.0 database and its filestore; run the upgrade on a copy.
2. Install the 18.0 trees, OpenUpgrade 18.0 at `fba9d88`, `openupgradelib` and the Python packages above in the 18.0
   environment; write the configuration above.
3. Run the upgrade on the copy:

   ```bash
   odoo-bin -c upgrade-18.conf -d <database> -u all --stop-after-init --no-http --log-level=info
   ```

4. Check the log for `ERROR` and `CRITICAL` records and the module states (`SELECT name, state FROM ir_module_module
   WHERE state NOT IN ('installed', 'uninstalled', 'uninstallable')` must return nothing), then read the `WARNING`
   lines of the scripts (`OpenUpgrade:` and `odoo.upgrade.lib` loggers): they name the records that need a decision
   (certificates whose key was not linked, policies or accounts that could not be mapped, switches that differed).
5. Review the items of [Known limitations](#known-limitations) that apply to the database.

## The base scripts

**`base/18.0.1.0/pre-migration.py`: the module map** (runs before the OpenUpgrade base pre-migration).

- Renames: `account_sepa` → `account_iso20022`, `hr_payroll_account_sepa` → `hr_payroll_account_iso20022`,
  `account_bacs` → `l10n_uk_bacs`, `l10n_au_keypay` → `l10n_employment_hero`.
- Merges of modules 18.0 folded into another one (their records keep their ids under the new owner and the 18.0 data
  updates them): `data_merge` → `data_cleaning`, `l10n_ch_hr_payroll_elm` → `l10n_ch_hr_payroll`,
  `stock_account_enterprise` → `stock_accountant`, `account_reports_tax_reminder` → `account_reports`,
  `documents_spreadsheet_account` and `documents_spreadsheet_crm` → `documents_spreadsheet`,
  `website_sale_renting_product_configurator` → `website_sale_renting`, `l10n_be_codabox_bridge` and
  `l10n_be_codabox_bridge_wizard` → `l10n_be_codabox`, `l10n_cl_edi_boletas` → `l10n_cl_edi`, `l10n_mx_edi_stock_30`,
  `l10n_mx_edi_stock_extended`, `l10n_mx_edi_stock_extended_30` and `l10n_mx_edi_stock_extended_31` →
  `l10n_mx_edi_stock`, `l10n_br_avatax_services` → `l10n_br_avatax` (its cities are handed to `l10n_br` first),
  `l10n_br_edi_services` → `l10n_br_edi`, `l10n_br_edi_sale_services` → `l10n_br_edi_sale`,
  `spreadsheet_dashboard_purchase` → `spreadsheet_dashboard`, `l10n_in_reports_debit_note` → `l10n_in_reports_gstr`,
  `l10n_fr_reports_extended` → `l10n_fr_reports`.
- Modules 18.0 removed without successor are merged into the 17.0 dependency that 18.0 keeps: their row goes, their
  updatable data is deleted by the update, their `noupdate` records stay under the target, their tables and columns
  stay (OpenUpgrade never drops them). Before the merge their scheduled actions are archived and the `noupdate` record
  rules that only serve their own groups become updatable, so the update deletes them before the groups.
  `account_consolidation` → `account_reports`, `account_taxcloud` → `l10n_us`, `sale_account_taxcloud` → `sale`,
  `sale_amazon_taxcloud` → `sale_amazon`, `sale_loyalty_taxcloud` → `sale_loyalty`, `sale_loyalty_taxcloud_delivery` →
  `sale_loyalty_delivery`, `sale_subscription_taxcloud` → `sale_subscription`, `website_sale_account_taxcloud` →
  `website_sale`, `sale_ebay` → `sale_management`, `l10n_account_customer_statements` → `account_reports`,
  `l10n_uk_customer_statements` → `l10n_uk`, `l10n_be_us_consolidation_demo` → `account_reports`, `l10n_dk_edi` →
  `l10n_dk`, `mrp_subcontracting_studio` → `mrp_subcontracting`, `website_twitter` (community, the dependency of the
  wall) and `website_twitter_wall` → `website`, `website_event_twitter_wall` → `website_event`.

**`base/18.0.1.0/post-migration.py`** (after the OpenUpgrade base pre-migration, before Odoo lists the modules):

- undoes the OpenUpgrade renames of Odoo modules that enterprise 18.0 still ships under their 17.0 name
  (`l10n_it_riba`, `spreadsheet_dashboard_purchase_stock`): a renamed `_oca` row whose module is not installable here
  gets its 17.0 name back when that name is installable and has the author of the 17.0 row;
- the uninstalled-modules guard: an uninstalled 17.0 row whose code is not installable on the 18.0 addons path becomes
  `uninstallable`, so a new dependency of an installed module (18.0 `account_budget` needs `purchase`) cannot
  auto-install it and leave it pending.

**`base/18.0.1.0/end-migration.py`**: converts the enterprise company-dependent fields (`lib/company_dependent`) after
every module is loaded and before the OpenUpgrade base end-migration removes the `ir.property` model; record values
become per-company jsonb values, default values become `ir.default`. Fields: follow-up date and responsible, payroll
structure journal and rule accounts, worksheet template of services, DATEV numbers and partner identifiers, Ecuadorian
withholding taxes, rental extra prices and preparation time, and the rows of Avatax, UPS, Belgian fleet and Brazilian
service codes.

## Coverage

Every module directory with a script: 75 directories with 99 scripts (54 pre-, 42 post- and 3 end-migrations) and
one `noupdate_changes.xml`; the version directory is the one Odoo runs between the 17.0 and the 18.0 version of the
module.

| module | version | scripts | what it does |
|---|---|---|---|
| `account_accountant` | 18.0.1.0 | pre | renames the deferred settings and gives deferred revenues the 17.0 deferred journal and method; renames moved xmlids; creates missing Kenyan tax tags; marks the new `accountant` application for installation; on a database where the upgrade installs the module, frees the three Ecuadorian group xmlids 18.0 uses for accounts and creates those accounts from the 18.0 chart |
| `account_asset` | 18.0.1.0 | pre, post | turns the asset model of each account into the 18.0 list of asset models |
| `account_asset_fleet` | 18.0.1.0 | pre | stores on each asset the vehicle it was bought for |
| `account_budget` | 18.0.1.0 | pre, post, end | renames the budget models, tables and columns to 18.0, maps the states, fills the new required columns, keeps the analytic account of each line and puts it in the column of its analytic plan; deletes an obsolete rule |
| `account_inter_company_rules` | 18.0.1.1 | pre, post | turns the invoice synchronization rule into the 18.0 bills switch |
| `account_iso20022` | 18.0.1.0 | pre | renames the 17.0 `account_sepa` fields (identification, LEI, batch booking, UETR) and the credit transfer method xmlid; maps the dropped pain versions |
| `account_reports` | 18.0.1.0 | pre, post | footnotes become annotations; profit and loss line codes, expressions and hierarchy follow 18.0; `last_*` opening filters become `previous_*`; tax closing entries get their report; tax report activities move to the journal |
| `account_sepa_direct_debit` | 18.0.1.0 | pre | moves the mandate from the journal entry to the payment; fills the new pre-notification period of mandates |
| `appointment` | 18.0.1.0 | pre, post | renames the manual confirmation of resource bookings; deletes the 17.0 onboarding |
| `appointment_crm` | 18.0.1.0 | post | keeps the Appointment tag on leads, only the xmlid goes |
| `approvals` | 18.0.1.0 | post | deletes the 17.0 approval request rules |
| `base` | 18.0.1.0 | pre, post, end | module map, OpenUpgrade renames undone, uninstalled-modules guard, company-dependent conversion (above) |
| `documents` | 18.0.1.0 | pre, post | turns workspaces into folders owned by OdooBot, maps workspace groups to internal access and member access rows, keeps the 17.0 administrators' reach, dedups tag names, remaps folder ids of linked modules, creates the server actions 18.0 data cannot create in an update |
| `frontdesk` | 18.0.1.0 | pre | gives each visitor the company of its station |
| `helpdesk` | 18.0.1.0 | pre | renames the views of the 7-day success action |
| `helpdesk_sale_timesheet` | 18.0.1.0 | post | moves the SLA policy of a service from the company-dependent product field to the policy's products; lists order line links no product explains |
| `hr_appraisal` | 18.0.1.1 | pre, post | creates the 18.0 appraisal templates from the 17.0 feedback templates, every language kept; departments without custom templates get their company's |
| `hr_appraisal_survey` | 18.0.1.2 | post | deletes the simple manager rules 18.0 renamed |
| `hr_contract_salary` | 18.0.2.0 | pre | inverts the hide-description flag of benefits; maps the color to the 18.0 highlight |
| `hr_payroll` | 18.0.1.0 | pre, post, end | custom salary attachment types become input types offered in attachments, attachments point at them; at the end, rules, categories and input types 18.0 drops stay, archived, while 17.0 payslips use them |
| `hr_payroll_account_iso20022` | 18.0.1.0 | pre | keeps the UETR of paid payslips under its 18.0 name |
| `hr_recruitment_extract` | 18.0.1.0 | post | gives each candidate the CV digitization state of its latest applicant |
| `hr_referral` | 18.0.1.0 | post | deletes the 17.0 points manager rule |
| `industry_fsm` | 18.0.1.0 | pre | hands the task report mail template, its report action and the report view to `industry_fsm`, which ships them in 18.0 |
| `industry_fsm_report` | 18.0.1.0 | pre | moves the task report mail template xmlid to `industry_fsm`, or drops the old one when it is already there |
| `iot` | 18.0.1.0 | pre | drops the 17.0 channel table and model, an abstract model in 18.0 |
| `l10n_ar_edi` | 18.0.1.1 | post | AFIP certificate and key of each company as 18.0 certificate records (`lib/certificate`) |
| `l10n_au_hr_payroll` | 18.0.1.0 | pre, post | renames and moves the contract fields 18.0 keeps on the employee, scales casual loadings to fractions, keeps the nine dropped structures with their rules archived and moves their contracts to the schedule 1 type |
| `l10n_au_hr_payroll_account` | 18.0.1.0 | post | gives SuperStream lines without account the employee's account at their payee fund, or an archived one |
| `l10n_be_codabox` | 18.0.1.0 | post | disconnects companies marked connected without token |
| `l10n_be_hr_payroll` | 18.0.1.0 | pre, post | ONSS certificate and key as 18.0 certificate records; moves the voluntary withholding rate from the contract to the employee |
| `l10n_ch_hr_payroll` | 18.0.1.0 | pre | stores the Swissdec institution code of every insurance |
| `l10n_cl_edi` | 18.0.1.2 | post | SII certificates (PFX and passphrase, owner, tokens) as 18.0 certificate records |
| `l10n_de_reports` | 18.0.1.0 | pre, post | keeps the DATEV partner identifiers for the company-dependent conversion; sets the DATEV deferred accounts of SKR03/SKR04 companies |
| `l10n_ec_edi` | 18.0.1.3 | pre, post | detaches the certificate many2one before the load, creates the 18.0 certificate records and relinks the companies |
| `l10n_employment_hero` | 18.0.1.0 | pre, post | renames the 17.0 keypay fields and payrun cron; the 17.0 API key and URL become company settings of the companies that use the integration |
| `l10n_in_reports_gstr` | 18.0.1.0 | post | keeps a company in production for GST returns when either 17.0 switch was on; lists companies whose switches differed |
| `l10n_ke_hr_payroll` | 18.0.1.0 | pre | the Kenyan disability exemption becomes the employee's disabled flag |
| `l10n_lu_hr_payroll` | 18.0.1.0 | pre, post | tax card number, vehicle benefit and travel expenses in their 18.0 fields; the CISSM parameter xmlid 18.0 renamed; tax ids of closed payslips; the total allowances rule 17.0 shipped archived is active |
| `l10n_mx_edi` | 18.0.0.3 | pre, post | detaches the invoice certificate many2one, creates the 18.0 certificate records and relinks the invoices; customer addenda become addenda records |
| `l10n_mx_edi_stock` | 18.0.1.2 | pre, post | the 3.0 customs regime of a picking becomes its regimes, the typed hazardous code the catalog entry, the packaging type of hazardous products is restored |
| `l10n_nl_reports_sbr` | 18.0.0.3 | post | Digipoort certificate, key and server root certificate as 18.0 certificate records |
| `l10n_pe_edi` | 18.0.0.1 | pre, post | detaches the certificate many2one, creates the 18.0 certificate records and relinks the companies |
| `mrp_mps` | 18.0.1.0 | pre | keeps the number of displayed columns of each company's period |
| `mrp_plm` | 18.0.1.0 | pre, post | remaps the displayed image of ECOs to the product documents OpenUpgrade made from the manufacturing documents, before the new foreign key; copies the attachment origin of the documents |
| `mrp_workorder_iot` | 18.0.1.0 | pre | gives the IoT trigger actions their 18.0 keys |
| `planning` | 18.0.1.0 | pre | end hour and day span of shift templates as 17.0 computed them on the company calendar; the self-unassign setting becomes a selection |
| `pos_pricer` | 18.0.1.0 | pre | moves Pricer tags and stores from templates to variants and queues the variants for Pricer |
| `pos_restaurant_appointment` | 18.0.1.0 | pre | keeps one appointment type per point of sale, the first active one |
| `pos_self_order_preparation_display` | 18.0.1.0.0 | pre | renames the take-away flag of preparation orders |
| `project_account_budget` | 18.0.1.0 | post | deletes the old demo budget lines |
| `project_forecast` | 18.0.1.0 | pre | the company-dependent project of shift templates becomes a plain many2one |
| `sale_purchase_inter_company_rules` | 18.0.1.1 | post | the order synchronization rule becomes the 18.0 order switches; automatic validation becomes the posted document state |
| `sale_renting` | 18.0.1.0 | post | deletes the xmlids of the 17.0 extra price defaults (the values go through the company-dependent conversion) |
| `sale_renting_sign` | 18.0.1.0 | post | links the signature requests of rental orders through `reference_doc` |
| `sale_stock_renting` | 18.0.1.0 | post | deletes the xmlid of the 17.0 preparation time default |
| `sale_subscription` | 18.0.1.0 | post | deletes the 17.0 payment success template |
| `sale_timesheet_enterprise` | 18.0.0.1 | pre, post | the leaderboard and rate groups become company settings, the groups are deleted |
| `sign` | 18.0.1.0 | pre | refused requests and signers are canceled; signers who ignored an open request are listed |
| `social` | 18.0.1.0 | pre | adds the split-per-network flag of posts and templates |
| `social_facebook` | 18.0.1.0 | pre | Facebook message and images from the 17.0 shared post content (`lib/social`) |
| `social_instagram` | 18.0.1.0 | pre | Instagram message and images from the 17.0 shared post content |
| `social_linkedin` | 18.0.0.1 | pre | LinkedIn message and images from the 17.0 shared post content |
| `social_push_notifications` | 18.0.1.0 | pre | push notification message from the 17.0 message |
| `social_twitter` | 18.0.1.0 | pre, post | X message and images from the 17.0 shared post content; the media and stream type get their X names (`noupdate_changes.xml`) |
| `spreadsheet_edition` | 18.0.1.0 | pre | revision uuids, and parent revisions as many2one instead of uuid text |
| `voip` | 18.0.2.0 | post | the 17.0 PBX settings become the default provider, users point at it |
| `web_studio` | 18.0.1.0 | pre | renames the approval group of approval rules; copies the users to notify into the 18.0 relation (`lib/relation`) |
| `website_delivery_sendcloud` | 18.0.1.0 | pre | pick-up radius in the 18.0 unit (`lib/delivery`) |
| `website_event` | 18.0.1.4 | post | removes the Social event pages of the removed Twitter wall module and their website menus |
| `website_sale_dashboard` | 18.0.1.0 | post | deletes the 17.0 onboarding |
| `website_sale_fedex` | 18.0.1.0 | pre | pick-up radius in the 18.0 unit |
| `website_sale_renting` | 18.0.1.0 | pre | gives every website the timezone 18.0 requires |
| `whatsapp` | 18.0.1.0 | pre | starts the reply window of conversations at the last answer of the WhatsApp partner |
| `worksheet` | 18.0.1.0 | pre | a template of one 17.0 company gets that company, others stay open to all companies |

## Known limitations

Each item is a decision or a known gap; the WARNING lines of the upgrade log name the affected records where a
script can see them.

**Certificates (AR, CL, EC, MX, NL, PE, BE payroll).**
- The 17.0 key and certificate files of Argentina, the Netherlands and Belgian payroll were company binary fields;
  their attachments stay in `ir_attachment` after the 18.0 certificate records are created. Deleting them is left to
  the database owner.
- A Dutch SBR key uploaded with a password is stored encrypted, and 17.0 never stored that password: the key is kept as
  a `certificate.key` that is not linked to its certificate (WARNING). Upload the key again in 18.0.
- A key that does not belong to its certificate is kept unlinked (WARNING); the certificate itself is always created.
- The Mexican addenda step of the `l10n_mx_edi` post-migration is not idempotent: do not run it a second time on the
  same database.

**Accounting.**
- The Kenyan tax tag step of the `account_accountant` pre-migration runs only when `account_accountant` was installed
  on 17.0; on a database where the upgrade installs it, the step does not run.
- Budgets: every 17.0 budget line becomes an expense line (`budget_type`), and a budget without dates gets its creation
  date and one year later as period; check revenue budgets after the upgrade.
- 17.0 draft batches of "generic" credit transfers keep the SEPA credit transfer method; 18.0 decides the format and
  the charge bearer by the payment method, so pick the ISO 20022 method before sending them.
- India: the GST return and e-invoicing production switches become one; a company is in production when either was,
  and companies whose switches differed are listed (WARNING).

**Documents.**
- The 18.0 tag set and the tag server actions and accounting folder actions of 18.0 are not created for a 17.0
  database (the data file creates them only on install; the actions that need the 18.0 tags are skipped and listed).
- 17.0 share links (`documents.share`) are not migrated: shared folders and documents have no link access in 18.0.
- The documents pre-migration is not idempotent: do not run it a second time on the same database.

**Payroll.**
- The generic payroll step (rules, categories and input types 18.0 drops stay archived while 17.0 payslips use them)
  is proven on Luxembourg payslips; Belgian, Swiss and Kenyan payslips are not recomputed by the test suite.
- Luxembourg: the extra holidays of 17.0 have no 18.0 field, and 18.0 rewrote the Luxembourg rules; review the
  contracts before the first 18.0 payslips.
- Australia: SuperStream lines whose account belongs to another fund than their payee are only listed (WARNING); the
  start date of super accounts, required in 18.0, is not filled where 17.0 left it empty.
- Switzerland: a database without the 17.0 ELM module keeps the Swissdec code as institution name, and the new
  required institution fields of LPP insurances stay empty; complete them in 18.0.

**Other modules.**
- Planning: the end hour of a shift template is computed for the day of the upgrade on the upgrading company's calendar
  and timezone, as 17.0 displayed it; a database whose users sat in several timezones saw different 17.0 values.
- Paid appointments: when a logged-in customer typed another phone number than their partner's for a pending paid
  booking, 17.0 kept it only in the booking description, which 18.0 drops; the answers and the partner's phone are kept.
- Company-dependent fields of Avatax, UPS, Belgian fleet and Brazilian service codes are converted by the shared step
  but not exercised by the test suite.

**Modules 18.0 removed (merged into the module that remains).**
- TaxCloud (`account_taxcloud` and its six bridges): the integration is gone (18.0 offers Avatax); API credentials,
  TaxCloud categories and the "Use TaxCloud API" flag stay in their columns without a field; the TaxCloud fiscal
  position and the taxes it created stay.
- `sale_ebay`: the eBay connector is gone; listings, categories, policies and sites stay in their tables without a
  model; the eBay sales team, product category, activity type, record rule, parameter and recovery action stay; the
  order and stock synchronizations stay archived.
- `l10n_account_customer_statements` and `l10n_uk_customer_statements`: the 17.0 statement report and its partner
  action go; 18.0 `account_reports` offers its own customer statement.
- `account_consolidation` and `l10n_be_us_consolidation_demo`: consolidation charts, periods and journals stay in their
  tables without a model; 18.0 does not migrate them, its consolidation works through shared accounts.
- `website_twitter`, `website_twitter_wall`, `website_event_twitter_wall`: Twitter walls and tweets stay in their tables
  without a model; the Social pages of events and their website menus are deleted.
- `l10n_dk_edi` and `mrp_subcontracting_studio`: empty in 17.0, nothing is lost; `l10n_fr_reports_extended`: folded
  into `l10n_fr_reports`, nothing is lost.

## Defects in Odoo and OpenUpgrade worked around here

Worth reporting upstream; each is compensated by the script named.

| where | defect | effect without the workaround | worked around in |
|---|---|---|---|
| OpenUpgrade 18.0 `apriori.py` | renames `l10n_it_riba` to `l10n_it_riba_oca` and `spreadsheet_dashboard_purchase(_stock)` to `*_oca`, modules of OCA repositories, although enterprise 18.0 ships `l10n_it_riba` and `spreadsheet_dashboard_purchase_stock` under their 17.0 name | installed: the module ends 'to upgrade' and the update ends with an ERROR, the real module comes back as a new uninstalled row; uninstalled: a stale `_oca` row that a new dependency can auto-install | `base` post-migration (rename undone), `base` pre-migration (vendors dashboard merged before the rename) |
| OpenUpgrade 18.0 `account` pre-migration | converts `account.report.default_opening_date_filter` from `previous_*` to `last_*`, the opposite of the 17.0 → 18.0 change | "Wrong value for account.report.default_opening_date_filter" when the ORM recomputes a report | `account_reports` pre-migration |
| OpenUpgrade 18.0 | lists `website_twitter` as removed without merging it | a 17.0 database with a Twitter wall keeps it 'to upgrade' | `base` pre-migration (merged into `website`) |
| openupgradelib `lift_constraints` | the incoming branch joins `confrelid` with `conkey`, so it also drops foreign keys of other tables that point at the table through a column with the same attribute number | random foreign keys of `res_company` or `account_move` dropped | `lib/schema.drop_foreign_keys` |
| openupgradelib `openupgrade_180.convert_company_dependent` | no marker (a second run overwrites 18.0 edits from the surviving `ir_property` table), record properties without company dropped, dangling many2one ids kept, booleans stored as 0/1 and dates as timestamps | lost or wrong company-dependent values | `lib/company_dependent` |
| Odoo 18.0 `account_accountant` | its post-install hook reloads the chart; the Ecuadorian 17.0 chart created `ec51020205`, `ec51030205` and `ec52010405` as account groups, the 18.0 chart as accounts | the upgrade aborts on an Ecuadorian database where it installs `account_accountant` | `account_accountant` pre-migration |
| Odoo 18.0 `l10n_in_reports` | depends on `sign`, so the upgrade auto-installs `documents_sign` next to `documents`, whose data refers to a `forcecreate="0"` `noupdate` server action of `documents` that an update never creates | CRITICAL "External ID not found" on an Indian database with Documents | `documents` post-migration (`lib/data`) |
| Odoo 18.0 `l10n_lu_hr_payroll` | ships the 2019 CISSM ceiling under a new xmlid for the parameter and date of the 17.0 value, against the uniqueness of (parameter, date) | the upgrade aborts on a Luxembourg payroll database | `l10n_lu_hr_payroll` pre-migration |
| Odoo 18.0 `l10n_lu_hr_payroll` | reuses the total allowances rule 17.0 shipped archived without setting `active` | allowances such as the transport fee deduction no longer lower the taxable amount | `l10n_lu_hr_payroll` post-migration |
| Odoo 18.0 payroll localizations | drop salary rules, categories and input types that 17.0 payslip lines still reference | ERROR "bad query: DELETE FROM hr_salary_rule …" and the dropped rules stay active | `hr_payroll` end-migration (`lib/payroll`) |
| Odoo 18.0 `account_consolidation` removal | the consolidation group is updatable while the record rule on companies that uses it is `noupdate`, and rule groups are `ondelete='restrict'` | ERROR "bad query: DELETE FROM res_groups …" at the end of the update | `base` pre-migration (rules of removed groups made updatable) |

## Testing

The `scripts/` directory holds an end-to-end suite: build a 17.0 database, seed it through the 17.0 ORM, upgrade it
with OpenUpgrade 18.0 and this repository, and check the result in SQL.

| file | role |
|---|---|
| `scripts/run_e2e_test.sh` | the runner: one database per call, phases 0 preflight (both Odoo versions probed without a database), 1 install on 17.0, 2 seed, 3 upgrade (`-u all` on 18.0 with the framework), 4 checks, 5 cleanup; exit 10–14 for the phase that failed; last line `RESULT db=… exit=… phase=… passed=… failed=… skipped=… errors=… critical=… allow_re=…` |
| `scripts/run_e2e_batches.sh` | the batches: runs the runner once per batch, one database `oue18_batch_<name>` at a time, and prints a table (exit, failing phase, checks passed / failed / skipped, ERROR / CRITICAL records, time) |
| `scripts/seed_v17.py` | the seed, run through `odoo-bin shell` on 17.0: one block per 17.0 module, run only where that module is installed; it writes through the ORM and records ids and expected 18.0 values in the table `oue18_seed (k, v)` |
| `scripts/verify_v18.sql` | the checks, run with `psql` on the upgraded database |

**Batches** (17.0 module names; each database installs the closure of its list, so it seeds and checks every scripted
module that list pulls in):

| batch | modules |
|---|---|
| `acc` | accounting: accountant, reports, assets (+fleet), budget (+project), SEPA credit transfer and direct debit, inter-company rules, follow-up, DATEV |
| `hr` | payroll (+accounting, +SEPA), appraisal (+survey), salary configurator, referral, CV digitization, planning, forecast |
| `pay` | Australian (+accounting, Employment Hero), Belgian, Swiss, Kenyan and Luxembourg payroll |
| `prod` | documents, spreadsheet, Studio, WhatsApp, VoIP, approvals, sign, IoT, MPS, work order IoT, PLM |
| `mkt` | social marketing: Facebook, Instagram, LinkedIn, push notifications, X |
| `svc` | appointment (+CRM), frontdesk, helpdesk (+timesheet billing), field service report (+sale), worksheet, timesheet leaderboard |
| `sale` | subscription, rental (+stock, +sign, +website), eCommerce dashboard, Sendcloud, FedEx, Pricer, restaurant appointments, preparation display, purchase dashboards |
| `sale_mi` | Sendcloud and FedEx in a database whose name ends in `_mi`, where the seed selects imperial units |
| `edi` | the certificate localizations together: Argentina, Chile, Mexico, Ecuador, Peru, Netherlands SBR, Belgian payroll |
| `edi_inv` | Ecuador and Peru on an invoicing database, where the upgrade installs `account_accountant` |
| `l10n` | merged and renamed localizations: Mexican stock (3.0, 3.1, foreign trade), Brazilian services, Italian Ri.Ba., CodaBox, Indian GST returns |
| `rem` | the modules 18.0 removed or folded: TaxCloud and its bridges, eBay, customer statements, BE/US consolidation demo, Danish EDI, French VAT reimbursement, subcontracting Studio, Twitter walls |

**Running.**

```bash
CONF17=/path/to/odoo-17.conf CONF18=/path/to/odoo-18.conf PYLIB=/path/to/extra-packages \
    scripts/run_e2e_batches.sh              # every batch
CONF17=… CONF18=… scripts/run_e2e_batches.sh hr edi   # the named batches
```

`CONF17` is a 17.0 configuration (database connection, the 17.0 addons path, `data_dir`); `CONF18` the upgrade
configuration of [How it combines with OpenUpgrade 18.0](#how-it-combines-with-openupgrade-180) with the same database
connection and `data_dir`.

| variable | meaning |
|---|---|
| `CONF17`, `CONF18` | required: the 17.0 and 18.0 configurations |
| `PYLIB` | optional directory appended to `PYTHONPATH` after the virtualenv's own packages, for `openupgradelib` and Python packages a virtualenv lacks |
| `ODOO17`, `ODOO18`, `VENV17`, `VENV18` | the 17.0 and 18.0 Odoo checkouts and virtualenvs (defaults in the runner header) |
| `DROP_DB_CMD` | optional executable called with the database name for every drop; without it the runner calls `dropdb` |
| `RUN_TAG` | suffix of the runner log and of a copy of every phase log, so several runs keep their evidence |
| `KEEP_DB` | `1` keeps the database and its filestore after the run (default: dropped, also on failure) |
| `ERROR_ALLOW_RE` | ERROR records of the upgrade log matching this regular expression are listed and do not fail the run; CRITICAL records always do. A validation run leaves it unset, and the table marks rows run with it |
| `BATCHES`, `BATCH_<NAME>` | the batches to run and the module list of a batch (`BATCH_HR=…` overrides `hr`; any other name runs when its variable is set) |
| `LOG_DIR`, `SEED_PY`, `VERIFY_SQL`, `BASE_SQL`, `SEED_SQL`, `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` | log directory, the seed and the checks (defaults: the files above), optional SQL run after the base install and before the seed, database connection (default from `CONF18`) |

One database exists per batch at a time; it must be named `oue18_<name>` and is dropped with its filestore at the end
of the run unless `KEEP_DB=1`.

**Checks.** Each check prints one row `<n> PASS|FAIL|SKIP <code> <description> | <actual value>`, then a `SUMMARY`.

- A check names the 18.0 module whose migration it proves (`mod:` need) and the seed values it reads; where the module
  is not installed or the seed block did not run, it is SKIP, so a check never passes for a module the database does
  not have.
- **FAIL** means the upgraded data differs from what the seed recorded as the expected 18.0 value, the check found no
  row, or its query raised. Aggregate checks require the seeded rows to be there, so none passes on an empty result.
  The actual value after `|` shows what the database holds.
- Phase 4 also fails on any ERROR or CRITICAL record of the upgrade log, a module left in a transitional state, a
  `base` version other than 18.0, or a missing or inconsistent `SUMMARY`. A batch is good when it exits 0 with phase
  `passed`.

**Validation.** The batches above were run on this branch's scripts and suite: all 12 exit 0 with phase `passed`, no
FAIL row and no ERROR or CRITICAL record in the upgrade log. The seed has 95 blocks and the checks file 188 checks, so
each batch prints 188 rows. Checks passed per batch: acc 31, hr 40, pay 48, prod 32, mkt 13, svc 22, sale 34, sale_mi
10, edi 67, edi_inv 26, l10n 41, rem 32 (396 PASS, 0 FAIL, 1860 SKIP); every one of the 75 script directories has a
check that passed in at least one batch.

## License

AGPL-3.0
