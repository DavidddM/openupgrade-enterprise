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
    # Reset noupdate on survey ir.rules that hr_appraisal_survey v17
    # modified to exclude appraisal surveys. In v18, survey module
    # handles its own rules differently, so let the standard update
    # restore original domain_force values.
    openupgrade.set_xml_ids_noupdate_value(env, "survey", _noupdate_reset, False)
    # Delete renamed ir.rule XML IDs (simple_manager -> employee_manager)
    openupgrade.delete_records_safely_by_xml_id(
        env,
        [
            "hr_appraisal_survey.survey_user_input_rule_appraisal_simple_manager",
            "hr_appraisal_survey.survey_user_input_line_rule_appraisal_simple_manager",
            "hr_appraisal_survey.survey_question_rule_appraisal_simple_manager",
        ],
    )
