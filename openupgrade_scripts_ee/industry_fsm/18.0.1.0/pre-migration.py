# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_xmlid_renames = [
    (
        "industry_fsm_report.mail_template_data_task_report",
        "industry_fsm.mail_template_data_task_report",
    ),
    ("industry_fsm_report.task_custom_report", "industry_fsm.task_custom_report"),
    ("industry_fsm_report.worksheet_custom", "industry_fsm.worksheet_custom"),
]


@openupgrade.migrate()
def migrate(env, version):
    """Hand the field service report records 18.0 moved over to industry_fsm.

    18.0 ships the task report mail template, its report action and the
    report's QWeb view in industry_fsm instead of industry_fsm_report, and
    industry_fsm loads first. Renamed before that load, the 17.0 template, a
    noupdate record the update does not touch, stays the one that is sent,
    with its report attached, and the report and its view are updated in
    place instead of being created again while the 17.0 ones are deleted.
    """
    openupgrade.rename_xmlids(env.cr, _xmlid_renames)
