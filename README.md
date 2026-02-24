# OpenUpgrade Scripts for Odoo Enterprise

Migration scripts for upgrading Odoo Enterprise modules from **v17 to v18**, following [OpenUpgrade](https://github.com/OCA/OpenUpgrade) conventions.

> **Note:** These scripts require a valid Odoo Enterprise subscription. This repository contains only migration logic, not Odoo source code.

## Requirements

- Python 3.10+
- [openupgradelib](https://github.com/OCA/openupgradelib): `pip install openupgradelib`
- [OpenUpgrade](https://github.com/OCA/OpenUpgrade) community 18.0 branch (provides the upgrade framework and community module scripts)
- Odoo Enterprise 18.0 source code (requires active subscription)

## Usage

Run the upgrade with both community and enterprise script paths:

```bash
odoo-bin \
    --load=web,openupgrade_framework \
    --upgrade-path=/path/to/OpenUpgrade/openupgrade_scripts/scripts,/path/to/openupgrade-enterprise/openupgrade_scripts_ee \
    --addons-path=/path/to/OpenUpgrade/addons,/path/to/enterprise,/path/to/OpenUpgrade \
    -d your_database \
    -u all \
    --stop-after-init
```

Key points:
- `--load=web,openupgrade_framework` is **mandatory** (loads the OpenUpgrade server framework)
- The `--upgrade-path` must include both the community OpenUpgrade scripts directory and this repository's `openupgrade_scripts_ee` directory
- The `--addons-path` must include the community OpenUpgrade repo (which provides the framework), enterprise addons, and any other addons paths

## Module Coverage

60 enterprise modules are covered, organized by category.

### Accounting & Finance (18 modules)

| Module | Scripts | Description |
|--------|---------|-------------|
| `account_accountant` | pre, post | Deferred expense field renames, xmlid migration, new `accountant` module dependency, Kenya tax tag pre-creation |
| `account_reports` | pre, post | P&L restructuring, footnote-to-annotation rename, expression engine changes, date filter direction fix, tax_closing_end_date preservation |
| `account_budget` | pre, post | Budget model restructuring and field migrations |
| `account_asset` | pre, post | Asset model field renames and deprecation method changes |
| `account_asset_fleet` | pre | Bridge module field adjustments for asset-fleet link |
| `account_inter_company_rules` | pre, post | Inter-company rule field and view migrations |
| `sale_purchase_inter_company_rules` | post | Sale/purchase inter-company bridge adjustments |
| `account_sepa_direct_debit` | pre | SEPA direct debit mandate field migrations |
| `account_iso20022` | pre, post | Renamed from `account_sepa`; payment mode and format migrations |
| `l10n_de_reports` | pre, post | DATEV identifier fields converted to company-dependent (INTEGER to JSONB) |
| `l10n_ar_edi` | post | Argentina EDI electronic invoicing adjustments |
| `l10n_cl_edi` | post | Chile EDI field and data migrations |
| `l10n_ec_edi` | post | Ecuador EDI adjustments |
| `l10n_mx_edi` | post | Mexico EDI CFDI format updates |
| `l10n_pe_edi` | post | Peru EDI field migrations |
| `l10n_nl_reports_sbr` | post | Netherlands SBR reporting adjustments |
| `spreadsheet_edition` | pre | Spreadsheet collaborative edition data migrations |
| `project_account_budget` | post | Project-budget bridge module adjustments |

### HR & Payroll (10 modules)

| Module | Scripts | Description |
|--------|---------|-------------|
| `hr_payroll` | pre, post | Payroll structure and rule field migrations |
| `hr_appraisal` | pre, post | Appraisal model field renames and workflow changes |
| `hr_appraisal_survey` | post | Appraisal-survey bridge adjustments |
| `hr_contract_salary` | pre | Salary contract field and advantage migrations |
| `hr_referral` | post | Employee referral program field updates |
| `l10n_au_hr_payroll` | pre, post | Australia payroll localization migrations |
| `l10n_be_hr_payroll` | pre, post | Belgium payroll localization migrations |
| `l10n_ch_hr_payroll` | pre | Switzerland payroll localization adjustments |
| `l10n_ke_hr_payroll` | pre | Kenya payroll localization; depends on tax tag pre-creation |
| `l10n_be_codabox` | post | Belgium CodaBox bank integration adjustments |

### Social & Marketing (6 modules)

| Module | Scripts | Description |
|--------|---------|-------------|
| `social` | pre | Base social module: adds `is_split_per_media` column for per-platform content |
| `social_facebook` | pre | Copies shared message/images to Facebook-specific fields |
| `social_instagram` | pre | Copies shared message/images to Instagram-specific fields |
| `social_linkedin` | pre | Copies shared message/images to LinkedIn-specific fields |
| `social_twitter` | pre, post | Copies shared message/images to Twitter-specific fields |
| `social_push_notifications` | pre | Copies shared message to push-notification-specific field |

### Sales & Subscriptions (8 modules)

| Module | Scripts | Description |
|--------|---------|-------------|
| `sale_timesheet_enterprise` | pre, post | Timesheet billing field and view migrations |
| `sale_subscription` | post | Subscription model field and workflow migrations |
| `sale_renting` | post | Rental order field adjustments |
| `sale_stock_renting` | post | Rental stock bridge module adjustments |
| `website_sale_renting` | pre | Website rental frontend adjustments |
| `website_sale_fedex` | pre | FedEx shipping integration field migrations |
| `website_delivery_sendcloud` | pre | Sendcloud delivery integration migrations |
| `website_sale_dashboard` | post | Sales dashboard widget and data migrations |

### Project & Services (3 modules)

| Module | Scripts | Description |
|--------|---------|-------------|
| `planning` | pre | Planning slot model field renames and restructuring |
| `project_forecast` | pre | Forecast model adjustments for planning integration |
| `industry_fsm_report` | pre | FSM report template xmlid migration with duplicate-key handling |

### Documents (1 module)

| Module | Scripts | Description |
|--------|---------|-------------|
| `documents` | pre, post | Document workspace, tag, and access field migrations |

### Helpdesk (2 modules)

| Module | Scripts | Description |
|--------|---------|-------------|
| `helpdesk` | pre | Xmlid renames for 7days_success action views |
| `helpdesk_sale_timesheet` | post | Helpdesk-timesheet bridge adjustments |

### Manufacturing (2 modules)

| Module | Scripts | Description |
|--------|---------|-------------|
| `mrp_mps` | pre | Master Production Schedule field migrations |
| `mrp_plm` | post | Product Lifecycle Management field updates |

### Other (10 modules)

| Module | Scripts | Description |
|--------|---------|-------------|
| `base` | pre | Module renames (account_sepa→account_iso20022, hr_payroll_account_sepa→hr_payroll_account_iso20022, account_bacs→l10n_uk_bacs, l10n_au_keypay→l10n_employment_hero) and merges (data_merge→data_cleaning, l10n_ch_hr_payroll_elm→l10n_ch_hr_payroll, stock_account_enterprise→stock_accountant, account_consolidation→account_reports, account_reports_tax_reminder→account_reports, documents_spreadsheet_{account,crm}→documents_spreadsheet, website_sale_renting_product_configurator→website_sale_renting) |
| `appointment` | pre, post | Appointment slot and booking field migrations |
| `appointment_crm` | post | Appointment-CRM bridge adjustments |
| `approvals` | post | Approval request field and category migrations |
| `voip` | post | VoIP provider model restructuring and field migrations |
| `whatsapp` | pre | WhatsApp messaging integration field adjustments |
| `web_studio` | pre | Studio customization data migrations |
| `worksheet` | pre | Worksheet template field adjustments |
| `frontdesk` | pre | Front desk visitor management field migrations |
| `iot` | pre | IoT box and device field migrations |

## Known Limitations

### 1. Community `apriori.py` spreadsheet dashboard rename bug

The community OpenUpgrade `apriori.py` renames `spreadsheet_dashboard_purchase` and `spreadsheet_dashboard_purchase_stock` to nonexistent `_oca` targets. The correct mapping should use `merged_modules` pointing to `spreadsheet_dashboard` in the community OpenUpgrade's `apriori.py`. This causes a harmless "inconsistent module states" warning during upgrade but does not block migration.

### 2. New v18 auto-install bridge modules

Orphaned v17 enterprise modules (`l10n_be_codabox_bridge`, `l10n_be_codabox_bridge_wizard`, `l10n_cl_edi_boletas`, `l10n_mx_edi_stock_30`) are now merged into their parent modules via the `base` pre-migration script.

### 3. `pdf417gen` optional library for `l10n_cl_edi`

The `l10n_cl_edi` module logs a non-critical error about the missing `pdf417gen` barcode library. This is a runtime dependency for Chilean electronic invoicing barcode generation and does not affect the migration itself. Install with `pip install pdf417gen` if needed.

### 4. `industry_fsm_report` duplicate key handling

If community OpenUpgrade scripts already moved the `mail_template_data_task_report` xmlid to the `industry_fsm` module, our script detects the conflict and deletes the old reference instead of attempting a rename that would fail. The ERROR log line that appears is caught and handled gracefully -- migration succeeds.

## Resolved Issues

These issues were discovered during development and are now handled by the migration scripts:

### Kenya tax tag pre-creation

The Kenya localization (`l10n_ke`) references tax tags (e.g., `-WH Sales`, `+16% Sales Tax`) in its template CSV but does not ship a data file to create them. On upgrade, `account_accountant`'s `post_init` hook calls `_deref_account_tags()` which expects tags to exist. **Fix**: The `account_accountant` pre-migration detects if `l10n_ke` is installed and pre-creates all 34 referenced tax tags before the hook runs.

### `default_opening_date_filter` direction fix

The community `account` pre-migration converts `previous_*` to `last_*` for the `default_opening_date_filter` field, but the actual 17.0-to-18.0 change requires the opposite direction (`last_*` to `previous_*`). **Fix**: The `account_reports` pre-migration corrects this by converting `last_*` to `previous_*`.

## Testing

An end-to-end test suite is included in the `scripts/` directory.

### Test scripts

| File | Purpose |
|------|---------|
| `scripts/run_e2e_test.sh` | Orchestrator: creates v17 DB, seeds data, runs upgrade, verifies results |
| `scripts/seed_test_data.sql` | SQL seed data that exercises every migration script path |
| `scripts/verify_migration.sql` | 54 SQL verification queries checking post-upgrade state |

### Running tests

```bash
DB_NAME=test_upgrade bash scripts/run_e2e_test.sh all
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_NAME` | `test_e2e_v17` | Database name for the test |
| `DB_HOST` | `db` | PostgreSQL host |
| `DB_USER` | `odoo` | PostgreSQL user |
| `DB_PASSWORD` | `odoo` | PostgreSQL password |
| `ODOO_DIR` | `/workspace/odoo` | Path to Odoo community source |
| `ENTERPRISE_DIR` | `/workspace/enterprise` | Path to Odoo enterprise addons |
| `OPENUPGRADE_DIR` | `/workspace/odoo/openupgrade18` | Path to OpenUpgrade 18.0 |
| `OUE_DIR` | `/workspace/odoo/openupgrade-enterprise` | Path to this repository |

### Expected results

- Phase 1: ~430 modules installed on v17
- Phase 2: Seed data inserted for all migration paths
- Phase 3: Upgrade completes without fatal errors
- Phase 4: 55/55 verification checks PASS

## License

AGPL-3.0
