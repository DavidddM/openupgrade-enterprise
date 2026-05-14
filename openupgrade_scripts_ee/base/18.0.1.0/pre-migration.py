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
    ("account_reports_tax_reminder", "account_reports"),
    ("documents_spreadsheet_account", "documents_spreadsheet"),
    ("documents_spreadsheet_crm", "documents_spreadsheet"),
    ("website_sale_renting_product_configurator", "website_sale_renting"),
    ("l10n_be_codabox_bridge", "l10n_be_codabox"),
    ("l10n_be_codabox_bridge_wizard", "l10n_be_codabox"),
    ("l10n_cl_edi_boletas", "l10n_cl_edi"),
    ("l10n_mx_edi_stock_30", "l10n_mx_edi_stock"),
    ("l10n_mx_edi_stock_extended", "l10n_mx_edi_stock"),
    ("l10n_mx_edi_stock_extended_30", "l10n_mx_edi_stock"),
    ("l10n_mx_edi_stock_extended_31", "l10n_mx_edi_stock"),
    ("l10n_br_avatax_services", "l10n_br_avatax"),
    ("l10n_br_edi_services", "l10n_br_edi"),
    ("l10n_br_edi_sale_services", "l10n_br_edi_sale"),
    ("spreadsheet_dashboard_purchase", "spreadsheet_dashboard"),
    ("l10n_in_reports_debit_note", "l10n_in_reports_gstr"),
    ("l10n_fr_reports_extended", "l10n_fr_reports"),
]

_removed_modules = [
    ("account_consolidation", "account_reports"),
    ("account_taxcloud", "l10n_us"),
    ("sale_account_taxcloud", "sale"),
    ("sale_amazon_taxcloud", "sale_amazon"),
    ("sale_loyalty_taxcloud", "sale_loyalty"),
    ("sale_loyalty_taxcloud_delivery", "sale_loyalty_delivery"),
    ("sale_subscription_taxcloud", "sale_subscription"),
    ("website_sale_account_taxcloud", "website_sale"),
    ("sale_ebay", "sale_management"),
    ("l10n_account_customer_statements", "account_reports"),
    ("l10n_uk_customer_statements", "l10n_uk"),
    ("l10n_be_us_consolidation_demo", "account_reports"),
    ("l10n_dk_edi", "l10n_dk"),
    ("mrp_subcontracting_studio", "mrp_subcontracting"),
    ("website_twitter", "website"),
    ("website_twitter_wall", "website"),
    ("website_event_twitter_wall", "website_event"),
]


def _archive_removed_crons(cr):
    """Archive the scheduled actions of the modules 18.0 removed.

    Their code calls methods 18.0 no longer has. Updatable ones are deleted
    at the end of the update anyway; ``noupdate`` ones (the eBay order and
    stock synchronizations) would stay active under the merge target and
    fail at every run.
    """
    openupgrade.logged_query(
        cr,
        """
        UPDATE ir_cron
        SET active = FALSE
        WHERE active
            AND id IN (
                SELECT res_id FROM ir_model_data
                WHERE model = 'ir.cron' AND module IN %s
            )
        """,
        (tuple(name for name, _target in _removed_modules),),
    )


def _release_removed_rules(cr):
    """Make the record rules that only serve groups of removed modules updatable.

    The update deletes the groups of a removed module, which are updatable,
    but a ``noupdate`` rule still pointing at one blocks the deletion (18.0
    rule groups are ``ondelete='restrict'``). Updatable, such a rule is
    deleted first, as an uninstall of the module would.
    """
    openupgrade.logged_query(
        cr,
        """
        UPDATE ir_model_data d
        SET noupdate = FALSE
        WHERE d.model = 'ir.rule'
            AND d.module IN %(removed)s
            AND d.noupdate
            AND EXISTS (SELECT 1 FROM rule_group_rel r WHERE r.rule_group_id = d.res_id)
            AND NOT EXISTS (
                SELECT 1
                FROM rule_group_rel r
                LEFT JOIN ir_model_data g
                    ON g.model = 'res.groups'
                    AND g.res_id = r.group_id
                    AND g.module IN %(removed)s
                WHERE r.rule_group_id = d.res_id AND g.id IS NULL
            )
        """,
        {"removed": tuple(name for name, _target in _removed_modules)},
    )


def _move_brazilian_cities(cr):
    """Hand the Brazilian cities of l10n_br_avatax_services over to l10n_br.

    17.0 ships its cities as ``l10n_br_avatax_services.city_br_*``; 18.0 ships
    the same ids with the same names and states as ``l10n_br.city_br_*``. Moved
    before the merge, the l10n_br load updates the 17.0 cities instead of
    creating copies, and the end of the update no longer deletes them, which
    would empty the city of every partner that uses one.
    """
    openupgrade.logged_query(
        cr,
        """
        UPDATE ir_model_data
        SET module = 'l10n_br'
        WHERE module = 'l10n_br_avatax_services'
            AND model = 'res.city'
            AND name NOT IN (SELECT name FROM ir_model_data WHERE module = 'l10n_br')
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    """Rename and merge the enterprise modules 18.0 renamed, merged or removed.

    A module 18.0 folded into another one is merged into it, so its records
    keep their ids under the new owner and the 18.0 data updates them instead
    of inserting duplicates (the Mexican customs regimes and document types,
    whose code is unique, and the Brazilian NCM service codes). A module
    removed without successor is merged into the 17.0 dependency that
    remains, so its row goes, its updatable data is deleted by the update and
    its ``noupdate`` records stay under the target; its scheduled actions are
    archived and the rules of its own groups made updatable first. This runs
    before the OpenUpgrade base pre-migration, so the purchase vendors
    dashboard, which 18.0 folds into the enterprise purchase dashboard, is
    gone before OpenUpgrade would rename it to a module this deployment does
    not ship.
    """
    openupgrade.update_module_names(env.cr, _renamed_modules)
    _move_brazilian_cities(env.cr)
    openupgrade.update_module_names(env.cr, _merged_modules, merge_modules=True)
    _archive_removed_crons(env.cr)
    _release_removed_rules(env.cr)
    openupgrade.update_module_names(env.cr, _removed_modules, merge_modules=True)
