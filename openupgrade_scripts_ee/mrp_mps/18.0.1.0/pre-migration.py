# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _migrate_manufacturing_period_to_display(env):
    """Migrate single manufacturing_period_to_display to 4 period-specific fields.

    In 17.0, res.company had a single manufacturing_period_to_display (Integer)
    field. In 18.0, this is split into manufacturing_period_to_display_year (3),
    _month (12), _week (12), _day (30). Copy the old value to the field matching
    the company's current manufacturing_period setting.
    """
    for period, default in [("year", 3), ("month", 12), ("week", 12), ("day", 30)]:
        openupgrade.logged_query(
            env.cr,
            f"""
            ALTER TABLE res_company
            ADD COLUMN IF NOT EXISTS manufacturing_period_to_display_{period}
            integer DEFAULT {default}
            """,
        )
    if openupgrade.column_exists(
        env.cr, "res_company", "manufacturing_period_to_display"
    ):
        for period in ("month", "week", "day"):
            openupgrade.logged_query(
                env.cr,
                f"""
                UPDATE res_company
                SET manufacturing_period_to_display_{period} =
                    manufacturing_period_to_display
                WHERE manufacturing_period = %s
                AND manufacturing_period_to_display IS NOT NULL
                """,
                (period,),
            )


@openupgrade.migrate()
def migrate(env, version):
    _migrate_manufacturing_period_to_display(env)
