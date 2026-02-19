# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _migrate_timesheet_groups_to_company_booleans(env):
    """Migrate implied_group settings to per-company booleans.

    In 17.0, res.config.settings had two Boolean fields with implied_group=
    pointing to hidden groups. When enabled, Odoo added them as implied groups
    of base.group_user via res_groups_implied_rel.

    In 18.0, these are replaced by res.company boolean fields:
    - group_timesheet_leaderboard_show_rates -> timesheet_show_rates
    - group_use_timesheet_leaderboard -> timesheet_show_leaderboard
    """
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE res_company
        ADD COLUMN IF NOT EXISTS timesheet_show_rates boolean DEFAULT FALSE
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE res_company
        ADD COLUMN IF NOT EXISTS timesheet_show_leaderboard boolean DEFAULT FALSE
        """,
    )
    for group_xmlid, column in [
        ("group_timesheet_leaderboard_show_rates", "timesheet_show_rates"),
        ("group_use_timesheet_leaderboard", "timesheet_show_leaderboard"),
    ]:
        openupgrade.logged_query(
            env.cr,
            f"""
            UPDATE res_company SET {column} = TRUE
            WHERE EXISTS (
                SELECT 1 FROM res_groups_implied_rel
                WHERE gid = (
                    SELECT res_id FROM ir_model_data
                    WHERE module = 'base' AND name = 'group_user'
                )
                AND hid = (
                    SELECT res_id FROM ir_model_data
                    WHERE module = 'sale_timesheet_enterprise'
                    AND name = %s
                )
            )
            """,
            (group_xmlid,),
        )


@openupgrade.migrate()
def migrate(env, version):
    _migrate_timesheet_groups_to_company_booleans(env)
