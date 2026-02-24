# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_noupdate_reset = [
    "survey.survey_user_input_rule_survey_manager",
    "survey.survey_user_input_rule_survey_user_cw",
    "survey.survey_user_input_rule_survey_user_read",
    "survey.survey_user_input_line_rule_survey_manager",
    "survey.survey_user_input_line_rule_survey_user_read",
    "survey.survey_user_input_line_rule_survey_user_cw",
]


@openupgrade.migrate()
def migrate(env, version):
    """Reset noupdate on survey ir.rules and delete renamed XML IDs.

    In v17, hr_appraisal_survey modified survey ir.rules to exclude appraisal
    surveys. In v18, the survey module handles its own rules differently, so
    we reset noupdate to let the standard update restore original domain_force
    values. Also delete renamed ir.rule XML IDs (simple_manager was renamed
    to employee_manager).
    """
    openupgrade.set_xml_ids_noupdate_value(env, "survey", _noupdate_reset, False)
    openupgrade.delete_records_safely_by_xml_id(
        env,
        [
            "hr_appraisal_survey.survey_user_input_rule_appraisal_simple_manager",
            "hr_appraisal_survey.survey_user_input_line_rule_appraisal_simple_manager",
            "hr_appraisal_survey.survey_question_rule_appraisal_simple_manager",
        ],
    )
