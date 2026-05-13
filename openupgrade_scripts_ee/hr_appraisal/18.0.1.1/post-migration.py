# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade
from psycopg2 import sql
from psycopg2.extras import Json

_TEMPLATE_FIELDS = (
    "appraisal_employee_feedback_template",
    "appraisal_manager_feedback_template",
)


def _english(value):
    """English text of a 17.0 translated Html value (any language without it)."""
    if not value:
        return ""
    return value.get("en_US") or next(iter(value.values()), "") or ""


def _create_template(env, description, company_id, employee, manager):
    """Create an appraisal template holding two 17.0 feedback bodies.

    The 17.0 bodies are translated Html columns, which come back from the
    database as dicts ({lang: html}); passed to ``create`` the 18.0 Html field
    would sanitize the dict and store "Unknown error when sanitizing". The
    record is created with the English bodies, then both columns receive the
    17.0 values of every language as they were stored (already sanitized by
    17.0).
    """
    template = env["hr.appraisal.template"].create(
        {
            "description": description,
            "company_id": company_id,
            _TEMPLATE_FIELDS[0]: _english(employee),
            _TEMPLATE_FIELDS[1]: _english(manager),
        }
    )
    for field, value in zip(_TEMPLATE_FIELDS, (employee, manager)):
        if value:
            env.cr.execute(
                sql.SQL(
                    "UPDATE hr_appraisal_template SET {} = %s WHERE id = %s"
                ).format(sql.Identifier(field)),
                (Json(value), template.id),
            )
    template.invalidate_recordset(list(_TEMPLATE_FIELDS))
    return template


def _create_appraisal_templates(env):
    """Move feedback templates from company/department to hr.appraisal.template.

    In v17, feedback HTML was stored directly on res.company and hr.department.
    In v18, a new hr.appraisal.template model holds the templates, and
    company/department point to it via M2O.

    Steps:
    1. Create a template for each company that has feedback content.
    2. Create one for each department with custom templates
       (custom_appraisal_templates=True).
    3. Point the other departments at their company's template, as the 18.0
       compute does; it ran while the companies had no template yet.

    A company or department that already points at a template is skipped, so
    a second run creates nothing.
    """
    legacy_emp = openupgrade.get_legacy_name("appraisal_employee_feedback_template")
    legacy_mgr = openupgrade.get_legacy_name("appraisal_manager_feedback_template")
    legacy_dept_emp = openupgrade.get_legacy_name("employee_feedback_template")
    legacy_dept_mgr = openupgrade.get_legacy_name("manager_feedback_template")
    legacy_custom = openupgrade.get_legacy_name("custom_appraisal_templates")
    env.cr.execute(
        f"""
        SELECT id, {legacy_emp}, {legacy_mgr}
        FROM res_company
        WHERE ({legacy_emp} IS NOT NULL OR {legacy_mgr} IS NOT NULL)
        AND appraisal_template_id IS NULL
        """
    )
    for company_id, emp_template, mgr_template in env.cr.fetchall():
        if not emp_template and not mgr_template:
            continue
        template = _create_template(
            env, "Migrated from v17", company_id, emp_template, mgr_template
        )
        env.cr.execute(
            "UPDATE res_company SET appraisal_template_id = %s WHERE id = %s",
            (template.id, company_id),
        )
    env.cr.execute(
        f"""
        SELECT d.id, d.company_id, d.{legacy_dept_emp}, d.{legacy_dept_mgr}
        FROM hr_department d
        WHERE d.{legacy_custom} = true
        AND (d.{legacy_dept_emp} IS NOT NULL OR d.{legacy_dept_mgr} IS NOT NULL)
        AND d.custom_appraisal_template_id IS NULL
        """
    )
    for dept_id, company_id, dept_emp, dept_mgr in env.cr.fetchall():
        if not dept_emp and not dept_mgr:
            continue
        template = _create_template(
            env, "Migrated from v17 (department)", company_id, dept_emp, dept_mgr
        )
        env.cr.execute(
            "UPDATE hr_department SET custom_appraisal_template_id = %s WHERE id = %s",
            (template.id, dept_id),
        )
    openupgrade.logged_query(
        env.cr,
        f"""
        UPDATE hr_department d
        SET custom_appraisal_template_id = c.appraisal_template_id
        FROM res_company c
        WHERE c.id = d.company_id
        AND c.appraisal_template_id IS NOT NULL
        AND d.custom_appraisal_template_id IS NULL
        AND NOT coalesce(d.{legacy_custom}, false)
        """,
    )
    env["res.company"].invalidate_model(["appraisal_template_id"])
    env["hr.department"].invalidate_model(["custom_appraisal_template_id"])


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
