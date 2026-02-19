# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_renamed_modules = [
    ("account_sepa", "account_iso20022"),
    ("hr_payroll_account_sepa", "hr_payroll_account_iso20022"),
    ("account_bacs", "l10n_uk_bacs"),
    ("l10n_au_keypay", "l10n_employment_hero"),
]

_merged_modules = [
    ("data_merge", "data_cleaning"),
    ("l10n_ch_hr_payroll_elm", "l10n_ch_hr_payroll"),
    ("stock_account_enterprise", "stock_accountant"),
    # account_consolidation was removed entirely in 18.0 (no replacement);
    # merge into account_reports (its direct dependency) to clean up state
    ("account_consolidation", "account_reports"),
    # account_reports_tax_reminder was merged into account_reports in 18.0
    # (module directory still has models/tests but no __manifest__.py)
    ("account_reports_tax_reminder", "account_reports"),
    # Removed in 18.0 — merge into parent dependency to clean up state
    ("documents_spreadsheet_account", "documents_spreadsheet"),
    ("documents_spreadsheet_crm", "documents_spreadsheet"),
    # Merged in 18.0 (commit 74e6363)
    ("website_sale_renting_product_configurator", "website_sale_renting"),
]


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.update_module_names(env.cr, _renamed_modules)
    openupgrade.update_module_names(env.cr, _merged_modules, merge_modules=True)
