# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_insurance_tables = [
    "l10n_ch_social_insurance",
    "l10n_ch_accident_insurance",
    "l10n_ch_additional_accident_insurance",
    "l10n_ch_compensation_fund",
    "l10n_ch_sickness_insurance",
]


def _populate_insurance_code(env):
    """Populate insurance_code from insurance_company on 5 insurance tables.

    In v17, insurance_code was a non-stored computed field derived from
    insurance_company. In v18, it is a required stored Char field.
    """
    for table in _insurance_tables:
        openupgrade.logged_query(
            env.cr,
            f"""
            ALTER TABLE {table}
            ADD COLUMN IF NOT EXISTS insurance_code varchar
            """,
        )
        openupgrade.logged_query(
            env.cr,
            f"""
            UPDATE {table}
            SET insurance_code = insurance_company
            WHERE insurance_code IS NULL
            """,
        )


@openupgrade.migrate()
def migrate(env, version):
    _populate_insurance_code(env)
