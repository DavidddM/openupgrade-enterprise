# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _preserve_datev_identifier_columns(env):
    if openupgrade.column_exists(env.cr, "res_partner", "l10n_de_datev_identifier"):
        openupgrade.copy_columns(
            env.cr,
            {"res_partner": [("l10n_de_datev_identifier", None, None)]},
        )
        openupgrade.logged_query(
            env.cr,
            "ALTER TABLE res_partner DROP COLUMN l10n_de_datev_identifier",
        )
    if openupgrade.column_exists(
        env.cr, "res_partner", "l10n_de_datev_identifier_customer"
    ):
        openupgrade.copy_columns(
            env.cr,
            {"res_partner": [("l10n_de_datev_identifier_customer", None, None)]},
        )
        openupgrade.logged_query(
            env.cr,
            "ALTER TABLE res_partner DROP COLUMN l10n_de_datev_identifier_customer",
        )


@openupgrade.migrate()
def migrate(env, version):
    _preserve_datev_identifier_columns(env)
