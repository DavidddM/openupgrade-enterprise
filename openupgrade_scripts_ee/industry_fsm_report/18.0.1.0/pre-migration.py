# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_xmlid_renames = [
    (
        "industry_fsm_report.mail_template_data_task_report",
        "industry_fsm.mail_template_data_task_report",
    ),
]


@openupgrade.migrate()
def migrate(env, version):
    """Move the ``mail_template_data_task_report`` xmlid from
    ``industry_fsm_report`` to ``industry_fsm``, handling the case where
    community OpenUpgrade scripts already created the target.

    If the target xmlid already exists (from a community upgrade), the old
    reference is deleted instead of renamed, avoiding a duplicate-key error.
    """
    env.cr.execute(
        """
        SELECT 1 FROM ir_model_data
        WHERE module = 'industry_fsm' AND name = 'mail_template_data_task_report'
        """
    )
    if env.cr.fetchone():
        # Target exists - delete the old one, keep the new
        openupgrade.logged_query(
            env.cr,
            """
            DELETE FROM ir_model_data
            WHERE module = 'industry_fsm_report'
            AND name = 'mail_template_data_task_report'
            """,
        )
    else:
        openupgrade.rename_xmlids(env.cr, _xmlid_renames)
