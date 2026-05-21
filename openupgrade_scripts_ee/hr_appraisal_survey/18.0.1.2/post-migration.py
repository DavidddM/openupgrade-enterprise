# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    """Delete the simple manager rules 18.0 renamed to employee manager rules.

    The survey rules 17.0 hr_appraisal_survey rewrote are left to the
    OpenUpgrade survey post-migration, which runs first: it gives the two
    manager rules their 18.0 domain and deletes the four user rules 18.0
    dropped, and the rules stay ``noupdate`` as 18.0 ships them.
    """
    openupgrade.delete_records_safely_by_xml_id(
        env,
        [
            "hr_appraisal_survey.survey_user_input_rule_appraisal_simple_manager",
            "hr_appraisal_survey.survey_user_input_line_rule_appraisal_simple_manager",
            "hr_appraisal_survey.survey_question_rule_appraisal_simple_manager",
        ],
    )
