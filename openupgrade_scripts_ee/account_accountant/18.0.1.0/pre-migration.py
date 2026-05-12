# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)

_EC_GROUP_ACCOUNT_IDS = ("ec51020205", "ec51030205", "ec52010405")

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

    We pre-create the full set of tag names referenced in
    l10n_ke/data/template/account.tax-ke.csv (each name appears in both +/-
    variants as is standard for Odoo tax tags). Tags that already exist are
    skipped via ON CONFLICT. Handles both varchar (v17 schema) and jsonb
    (after base upgrade converts translatable fields) name column formats.
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
    tag_base_names = [
        "16% Sales Base",
        "16% Sales Tax",
        "8% Sales Base",
        "8% Sales Tax",
        "16% Purchases Base",
        "16% Purchases Tax",
        "8% Purchases Tax",
        "8% purchases Base",
        "Zero Rated Sales Base",
        "Zero Rated Purchases Base",
        "Exempt Sales Base",
        "Exempt Purchases Base",
        "Import Base",
        "Import Tax",
        "WH Sales",
        "WH base",
        "WH 2%",
    ]
    tag_names = []
    for base in tag_base_names:
        tag_names.append("+" + base)
        tag_names.append("-" + base)
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


def _ec_group_xmlids_to_legacy(cr):
    """Move the 17.0 Ecuadorian group xmlids that 18.0 uses for accounts.

    Returns the ids of the companies whose xmlids moved. A chart record's xmlid
    is ``account.<company id>_<template id>`` whatever its model; the 17.0
    l10n_ec chart creates ec51020205, ec51030205 and ec52010405 as account
    groups, the 18.0 chart as accounts. The groups keep their records under
    legacy xmlids, so the 18.0 chart loader no longer finds a group where it
    expects an account.
    """
    pattern = "^[0-9]+_(%s)$" % "|".join(_EC_GROUP_ACCOUNT_IDS)
    openupgrade.logged_query(
        cr,
        """
        UPDATE ir_model_data imd
        SET name = %(prefix)s || imd.name
        WHERE imd.module = 'account' AND imd.model = 'account.group'
            AND imd.name ~ %(pattern)s
            AND NOT EXISTS (
                SELECT 1 FROM ir_model_data d
                WHERE d.module = 'account' AND d.name = %(prefix)s || imd.name
            )
        """,
        {"prefix": openupgrade.get_legacy_name(""), "pattern": pattern},
    )
    cr.execute(
        """
        SELECT DISTINCT substring(name from %s)::integer
        FROM ir_model_data
        WHERE module = 'account' AND model = 'account.group' AND name ~ %s
        """,
        (
            "^%s([0-9]+)_" % openupgrade.get_legacy_name(""),
            "^%s[0-9]+_(%s)$"
            % (openupgrade.get_legacy_name(""), "|".join(_EC_GROUP_ACCOUNT_IDS)),
        ),
    )
    return [company_id for (company_id,) in cr.fetchall()]


def _load_ec_template_accounts(env, company):
    """Create or link the three accounts the 18.0 Ecuadorian chart expects.

    Goes through the chart loader as a chart reload does: an existing account
    with the template code gets the xmlid, otherwise the account is created
    from the 18.0 template with its name in every installed language.
    """
    chart = env["account.chart.template"].with_company(company)
    chart = chart.with_context(
        default_company_id=company.id,
        allowed_company_ids=[company.id],
        tracking_disable=True,
        lang="en_US",
        chart_template_load=True,
    )
    data = chart._get_chart_template_data(company.chart_template)
    template_data = data.pop("template_data", {})
    accounts = {
        xmlid: values
        for xmlid, values in data.get("account.account", {}).items()
        if xmlid in _EC_GROUP_ACCOUNT_IDS
        and not chart.ref(xmlid, raise_if_not_found=False)
    }
    if not accounts:
        return
    templates = {xmlid: dict(values) for xmlid, values in accounts.items()}
    load = {"account.account": accounts}
    chart._pre_reload_data(company, template_data, load)
    created = [
        xmlid
        for xmlid in load["account.account"]
        if not chart.ref(xmlid, raise_if_not_found=False)
    ]
    if load["account.account"]:
        chart._load_data(load)
    langs = [code for code, _name in env["res.lang"].get_installed()]
    for xmlid, values in templates.items():
        account = chart.ref(xmlid, raise_if_not_found=False)
        if not account:
            continue
        translations = {
            lang: chart._get_field_translation(values, "name", lang)
            for lang in langs
            if lang != "en_US"
        }
        translations = {lang: value for lang, value in translations.items() if value}
        if translations and xmlid in created:
            account.update_field_translations("name", translations)
        _logger.info(
            "EC chart of company %s: %s %s account %s (%s)",
            company.id,
            xmlid,
            "created as" if xmlid in created else "linked to",
            account.id,
            account.code,
        )


def _ec_chart_accounts(env):
    """Let the 18.0 chart loader find accounts behind the three EC chart ids.

    Runs on install and on update: the post_init hook of a newly installed
    account_accountant reloads every company's chart, and any later chart
    reload does the same.
    """
    for company_id in _ec_group_xmlids_to_legacy(env.cr):
        company = env["res.company"].browse(company_id).exists()
        if company and company.chart_template == "ec":
            _load_ec_template_accounts(env, company)


@openupgrade.migrate(no_version=True)
def migrate(env, version):
    """Migrate the accountant settings; on a new install only the EC chart step.

    The other steps need 17.0 account_accountant data, which a database that
    gets the module during the upgrade does not have.
    """
    _ec_chart_accounts(env)
    if not version:
        return
    openupgrade.rename_fields(env, _field_renames)
    openupgrade.rename_xmlids(env.cr, _xmlid_renames)
    _create_missing_l10n_ke_tax_tags(env)
    _ensure_accountant_module(env)
