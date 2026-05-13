# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _migrate_salary_attachment_types(env):
    """Migrate deduction_type_id -> other_input_type_id on hr.salary.attachment.

    The old hr.salary.attachment.type model was replaced by
    hr.payslip.input.type with available_in_attachments=True.
    Standard records share the same code (ATTACH_SALARY, ASSIG_SALARY,
    CHILD_SUPPORT). Custom records are migrated by creating new
    hr.payslip.input.type entries.

    Steps:
    1. Offer in attachments the input types that already have the code of an
       attachment type (17.0 pays an attachment through the input type of
       the same code and refuses to compute a payslip without one, so this
       is the usual case), with the type's no-end-date default.
    2. Migrate custom attachment types without such an input type by
       inserting them into hr_payslip_input_type: the English name (the
       17.0 name is translated, the 18.0 one is not) and ``active`` set,
       since the load fills the defaults of new columns before this script.
    3. Map old deduction_type_id to new other_input_type_id via code match,
       to the lowest id as 17.0 did.
    """
    legacy_col = openupgrade.get_legacy_name("deduction_type_id")
    if openupgrade.table_exists(env.cr, "hr_salary_attachment_type"):
        openupgrade.logged_query(
            env.cr,
            """
            UPDATE hr_payslip_input_type pit
            SET available_in_attachments = true,
                default_no_end_date = coalesce(pit.default_no_end_date, false)
                    OR coalesce(sat.no_end_date, false)
            FROM hr_salary_attachment_type sat
            WHERE pit.code = sat.code
            AND NOT coalesce(pit.available_in_attachments, false)
            """,
        )
        openupgrade.logged_query(
            env.cr,
            """
            INSERT INTO hr_payslip_input_type (
                name, code, country_id, available_in_attachments,
                default_no_end_date, active, is_quantity, create_uid, create_date,
                write_uid, write_date
            )
            SELECT
                COALESCE(
                    sat.name ->> 'en_US',
                    (SELECT v FROM jsonb_each_text(sat.name) AS j(k, v) LIMIT 1)
                ),
                sat.code, sat.country_id, true,
                COALESCE(sat.no_end_date, false), true, false,
                COALESCE(sat.create_uid, 1), COALESCE(sat.create_date, now()),
                COALESCE(sat.write_uid, 1), COALESCE(sat.write_date, now())
            FROM hr_salary_attachment_type sat
            WHERE NOT EXISTS (
                SELECT 1 FROM hr_payslip_input_type pit
                WHERE pit.code = sat.code
            )
            """,
        )
    openupgrade.logged_query(
        env.cr,
        f"""
        UPDATE hr_salary_attachment sa
        SET other_input_type_id = pit.id
        FROM hr_salary_attachment_type sat
        JOIN LATERAL (
            SELECT min(id) AS id FROM hr_payslip_input_type
            WHERE code = sat.code
        ) pit ON pit.id IS NOT NULL
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
