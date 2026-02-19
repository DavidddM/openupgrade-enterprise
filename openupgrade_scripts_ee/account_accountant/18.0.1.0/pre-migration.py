# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_field_renames = [
    (
        "res.company",
        "res_company",
        "deferred_journal_id",
        "deferred_expense_journal_id",
    ),
    (
        "res.company",
        "res_company",
        "deferred_amount_computation_method",
        "deferred_expense_amount_computation_method",
    ),
]

_xmlid_renames = [
    ("account_accountant.menu_accounting", "accountant.menu_accounting"),
]


def _create_missing_l10n_ke_tax_tags(env):
    """Pre-create Kenya (l10n_ke) tax tags that are missing from the localization.

    The l10n_ke module references tax tags in its tax template CSV
    (data/template/account.tax-ke.csv) but unlike other localizations, it does
    not ship an account.account.tag data file to create them. On a fresh 18.0
    install this is handled internally by the chart template loading, but on
    upgrade the account_accountant post_init hook calls _deref_account_tags()
    which expects tags to already exist, raising:
        UserError: missing tax tag -WH Sales for country Kenya

    We pre-create the full set of referenced tags here (before post_init runs).
    Tags that already exist are skipped via ON CONFLICT.
    """
    env.cr.execute(
        "SELECT id FROM ir_module_module WHERE name = 'l10n_ke' AND state IN %s",
        (("installed", "to install", "to upgrade"),),
    )
    if not env.cr.fetchone():
        return
    env.cr.execute(
        "SELECT id FROM res_country WHERE code = 'KE'",
    )
    row = env.cr.fetchone()
    if not row:
        return
    country_id = row[0]
    # Full set of tag names referenced in l10n_ke/data/template/account.tax-ke.csv.
    # Each name appears in both +/- variants as is standard for Odoo tax tags.
    tag_base_names = [
        "16% Sales Base", "16% Sales Tax",
        "8% Sales Base", "8% Sales Tax",
        "16% Purchases Base", "16% Purchases Tax",
        "8% Purchases Tax", "8% purchases Base",
        "Zero Rated Sales Base", "Zero Rated Purchases Base",
        "Exempt Sales Base", "Exempt Purchases Base",
        "Import Base", "Import Tax",
        "WH Sales", "WH base", "WH 2%",
    ]
    tag_names = []
    for base in tag_base_names:
        tag_names.append("+" + base)
        tag_names.append("-" + base)
    # The name column may be varchar (v17 schema) or jsonb (after base upgrade
    # converts translatable fields). Detect which format to use.
    env.cr.execute(
        """
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'account_account_tag' AND column_name = 'name'
        """,
    )
    is_jsonb = env.cr.fetchone()[0] == "jsonb"
    for tag_name in tag_names:
        if is_jsonb:
            openupgrade.logged_query(
                env.cr,
                """
                INSERT INTO account_account_tag
                    (name, applicability, country_id, active,
                     create_uid, create_date, write_uid, write_date)
                SELECT jsonb_build_object('en_US', %(name)s),
                       'taxes', %(country_id)s, true, 1, NOW(), 1, NOW()
                WHERE NOT EXISTS (
                    SELECT 1 FROM account_account_tag
                    WHERE name->>'en_US' = %(name)s
                      AND applicability = 'taxes'
                      AND country_id = %(country_id)s
                )
                """,
                {"name": tag_name, "country_id": country_id},
            )
        else:
            openupgrade.logged_query(
                env.cr,
                """
                INSERT INTO account_account_tag
                    (name, applicability, country_id, active,
                     create_uid, create_date, write_uid, write_date)
                SELECT %(name)s, 'taxes', %(country_id)s, true,
                       1, NOW(), 1, NOW()
                WHERE NOT EXISTS (
                    SELECT 1 FROM account_account_tag
                    WHERE name = %(name)s
                      AND applicability = 'taxes'
                      AND country_id = %(country_id)s
                )
                """,
                {"name": tag_name, "country_id": country_id},
            )


def _ensure_accountant_module(env):
    """Mark the ``accountant`` module for installation if not already installed.

    In v18, ``account_accountant`` depends on the new ``accountant`` module
    which must be present for the upgrade to complete.
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE ir_module_module
        SET state = 'to install'
        WHERE name = 'accountant'
        AND state IN ('uninstalled', 'uninstallable')
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_fields(env, _field_renames)
    openupgrade.rename_xmlids(env.cr, _xmlid_renames)
    _create_missing_l10n_ke_tax_tags(env)
    _ensure_accountant_module(env)
