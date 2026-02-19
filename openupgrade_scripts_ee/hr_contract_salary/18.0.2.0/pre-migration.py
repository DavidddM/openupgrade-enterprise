# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_column_renames = {
    "hr_contract_salary_benefit": [
        ("hide_description", None),
    ],
    "hr_contract_salary_benefit_value": [
        ("hide_description", None),
        ("color", None),
    ],
}


def _invert_hide_description(env):
    """Invert hide_description -> always_show_description on both tables."""
    for table in ("hr_contract_salary_benefit", "hr_contract_salary_benefit_value"):
        legacy_col = openupgrade.get_legacy_name("hide_description")
        openupgrade.logged_query(
            env.cr,
            f"""
            ALTER TABLE {table}
            ADD COLUMN IF NOT EXISTS always_show_description boolean
            """,
        )
        openupgrade.logged_query(
            env.cr,
            f"""
            UPDATE {table}
            SET always_show_description = NOT COALESCE({legacy_col}, false)
            """,
        )


def _remap_color_to_selector_highlight(env):
    """Remap color (green/red) -> selector_highlight (none/red)."""
    legacy_col = openupgrade.get_legacy_name("color")
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE hr_contract_salary_benefit_value
        ADD COLUMN IF NOT EXISTS selector_highlight varchar
        """,
    )
    openupgrade.logged_query(
        env.cr,
        f"""
        UPDATE hr_contract_salary_benefit_value
        SET selector_highlight = CASE
            WHEN {legacy_col} = 'red' THEN 'red'
            ELSE 'none'
        END
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_columns(env.cr, _column_renames)
    _invert_hide_description(env)
    _remap_color_to_selector_highlight(env)
