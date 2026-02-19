# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _create_appraisal_templates(env):
    """Migrate feedback templates from res.company/hr.department to hr.appraisal.template.

    In v17, feedback HTML was stored directly on res.company and hr.department.
    In v18, a new hr.appraisal.template model holds the templates, and
    company/department point to it via M2O.
    """
    legacy_emp = openupgrade.get_legacy_name("appraisal_employee_feedback_template")
    legacy_mgr = openupgrade.get_legacy_name("appraisal_manager_feedback_template")
    legacy_dept_emp = openupgrade.get_legacy_name("employee_feedback_template")
    legacy_dept_mgr = openupgrade.get_legacy_name("manager_feedback_template")
    legacy_custom = openupgrade.get_legacy_name("custom_appraisal_templates")
    # Create a template for each company that has custom feedback content
    env.cr.execute(
        f"""
        SELECT id, {legacy_emp}, {legacy_mgr}
        FROM res_company
        WHERE {legacy_emp} IS NOT NULL
        OR {legacy_mgr} IS NOT NULL
        """
    )
    AppraisalTemplate = env["hr.appraisal.template"]
    for company_id, emp_template, mgr_template in env.cr.fetchall():
        if not emp_template and not mgr_template:
            continue
        template = AppraisalTemplate.create(
            {
                "description": "Migrated from v17",
                "appraisal_employee_feedback_template": emp_template or "",
                "appraisal_manager_feedback_template": mgr_template or "",
                "company_id": company_id,
            }
        )
        env.cr.execute(
            "UPDATE res_company SET appraisal_template_id = %s WHERE id = %s",
            (template.id, company_id),
        )
    # Handle departments with custom templates
    env.cr.execute(
        f"""
        SELECT d.id, d.company_id, d.{legacy_dept_emp}, d.{legacy_dept_mgr}
        FROM hr_department d
        WHERE d.{legacy_custom} = true
        AND (d.{legacy_dept_emp} IS NOT NULL OR d.{legacy_dept_mgr} IS NOT NULL)
        """
    )
    for dept_id, company_id, dept_emp, dept_mgr in env.cr.fetchall():
        if not dept_emp and not dept_mgr:
            continue
        template = AppraisalTemplate.create(
            {
                "description": "Migrated from v17 (department)",
                "appraisal_employee_feedback_template": dept_emp or "",
                "appraisal_manager_feedback_template": dept_mgr or "",
                "company_id": company_id,
            }
        )
        env.cr.execute(
            "UPDATE hr_department SET custom_appraisal_template_id = %s WHERE id = %s",
            (template.id, dept_id),
        )


def _delete_obsolete_records(env):
    openupgrade.delete_records_safely_by_xml_id(
        env,
        [
            "hr_appraisal.hr_appraisal_implicit_rule",
            "hr_appraisal.hr_appraisal_employee_feedback",
            "hr_appraisal.hr_appraisal_manager_feedback",
        ],
    )


@openupgrade.migrate()
def migrate(env, version):
    _create_appraisal_templates(env)
    _delete_obsolete_records(env)
