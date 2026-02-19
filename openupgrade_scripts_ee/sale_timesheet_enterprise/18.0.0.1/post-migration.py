# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _delete_obsolete_records(env):
    openupgrade.delete_records_safely_by_xml_id(
        env,
        [
            "sale_timesheet_enterprise.group_timesheet_leaderboard_show_rates",
            "sale_timesheet_enterprise.group_use_timesheet_leaderboard",
        ],
    )


@openupgrade.migrate()
def migrate(env, version):
    _delete_obsolete_records(env)
