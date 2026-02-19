# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _migrate_salary_attachment_types(env):
    """Migrate deduction_type_id -> other_input_type_id on hr.salary.attachment.

    The old hr.salary.attachment.type model was replaced by
    hr.payslip.input.type with available_in_attachments=True.
    Standard records share the same code (ATTACH_SALARY, ASSIG_SALARY,
    CHILD_SUPPORT). Custom records are migrated by creating new
    hr.payslip.input.type entries.
    """
    legacy_col = openupgrade.get_legacy_name("deduction_type_id")
    # First, migrate custom attachment types that don't match standard codes
    if openupgrade.table_exists(env.cr, "hr_salary_attachment_type"):
        openupgrade.logged_query(
            env.cr,
            """
            INSERT INTO hr_payslip_input_type (
                name, code, country_id, available_in_attachments,
                default_no_end_date, create_uid, create_date,
                write_uid, write_date
            )
            SELECT
                sat.name, sat.code, sat.country_id, true,
                COALESCE(sat.no_end_date, false),
                COALESCE(sat.create_uid, 1), COALESCE(sat.create_date, now()),
                COALESCE(sat.write_uid, 1), COALESCE(sat.write_date, now())
            FROM hr_salary_attachment_type sat
            WHERE NOT EXISTS (
                SELECT 1 FROM hr_payslip_input_type pit
                WHERE pit.code = sat.code
            )
            """,
        )
    # Map old deduction_type_id to new other_input_type_id via code match
    openupgrade.logged_query(
        env.cr,
        f"""
        UPDATE hr_salary_attachment sa
        SET other_input_type_id = pit.id
        FROM hr_salary_attachment_type sat
        JOIN hr_payslip_input_type pit ON pit.code = sat.code
        WHERE sa.{legacy_col} = sat.id
        AND sa.other_input_type_id IS NULL
        """,
    )


def _delete_obsolete_records(env):
    openupgrade.delete_records_safely_by_xml_id(
        env,
        [
            "hr_payroll.group_hr_payroll_employee_manager",
        ],
    )


@openupgrade.migrate()
def migrate(env, version):
    _migrate_salary_attachment_types(env)
    _delete_obsolete_records(env)
