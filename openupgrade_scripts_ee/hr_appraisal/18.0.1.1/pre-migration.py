# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_column_renames = {
    "res_company": [
        ("appraisal_employee_feedback_template", None),
        ("appraisal_manager_feedback_template", None),
    ],
    "hr_department": [
        ("employee_feedback_template", None),
        ("manager_feedback_template", None),
        ("custom_appraisal_templates", None),
    ],
}


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_columns(env.cr, _column_renames)
