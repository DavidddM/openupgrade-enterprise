# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_field_renames = [
    ("res.company", "res_company", "l10n_au_kp_enable", "employment_hero_enable"),
    (
        "res.company",
        "res_company",
        "l10n_au_kp_identifier",
        "employment_hero_identifier",
    ),
    (
        "res.company",
        "res_company",
        "l10n_au_kp_lock_date",
        "employment_hero_lock_date",
    ),
    (
        "res.company",
        "res_company",
        "l10n_au_kp_journal_id",
        "employment_hero_journal_id",
    ),
    (
        "account.move",
        "account_move",
        "l10n_au_kp_payrun_identifier",
        "employment_hero_payrun_identifier",
    ),
    (
        "account.account",
        "account_account",
        "l10n_au_kp_account_identifier",
        "employment_hero_account_identifier",
    ),
    (
        "account.tax",
        "account_tax",
        "l10n_au_kp_tax_identifier",
        "employment_hero_tax_identifier",
    ),
]

_xmlid_renames = [
    (
        "l10n_employment_hero.keypay_sync_cron",
        "l10n_employment_hero.employment_hero_sync_cron",
    ),
]


@openupgrade.migrate()
def migrate(env, version):
    """Give the 17.0 keypay fields and payrun cron their 18.0 names.

    The base pre-migration renamed l10n_au_keypay to l10n_employment_hero;
    18.0 renamed its seven stored fields from ``l10n_au_kp_*`` to
    ``employment_hero_*`` and its cron xmlid. Without the renames the company
    settings, the payrun ids of the imported moves and the account and tax
    matchings would stay in columns 18.0 no longer reads, the next sync would
    import every payrun again, and a second cron would be created next to the
    17.0 one.
    """
    openupgrade.rename_fields(env, _field_renames)
    openupgrade.rename_xmlids(env.cr, _xmlid_renames)
