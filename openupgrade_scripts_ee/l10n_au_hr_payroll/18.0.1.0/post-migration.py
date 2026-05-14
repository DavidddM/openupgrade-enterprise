# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _get_contract_legacy(name):
    return openupgrade.get_legacy_name(name)


def _move_withholding_variation(env):
    """Move l10n_au_withholding_variation from contract to employee.

    v17: Boolean on hr.contract (True = variation applies)
    v18: Selection on hr.employee ('none'/'salaries'/'leaves')
    """
    legacy_col = _get_contract_legacy("l10n_au_withholding_variation")
    legacy_amt = _get_contract_legacy("l10n_au_withholding_variation_amount")
    openupgrade.logged_query(
        env.cr,
        f"""
        UPDATE hr_employee e
        SET l10n_au_withholding_variation = CASE
                WHEN c.{legacy_col} = true THEN 'salaries'
                ELSE 'none'
            END,
            l10n_au_withholding_variation_amount = c.{legacy_amt}
        FROM (
            SELECT DISTINCT ON (employee_id)
                employee_id, {legacy_col}, {legacy_amt}
            FROM hr_contract
            WHERE {legacy_col} IS NOT NULL
            ORDER BY employee_id,
                CASE WHEN state = 'open' THEN 0 ELSE 1 END,
                date_start DESC NULLS LAST
        ) c
        WHERE e.id = c.employee_id
        """,
    )


def _move_employment_basis_code(env):
    """Move l10n_au_employment_basis_code from contract to employee."""
    legacy_col = _get_contract_legacy("l10n_au_employment_basis_code")
    openupgrade.logged_query(
        env.cr,
        f"""
        UPDATE hr_employee e
        SET l10n_au_employment_basis_code = c.{legacy_col}
        FROM (
            SELECT DISTINCT ON (employee_id)
                employee_id, {legacy_col}
            FROM hr_contract
            WHERE {legacy_col} IS NOT NULL
            ORDER BY employee_id,
                CASE WHEN state = 'open' THEN 0 ELSE 1 END,
                date_start DESC NULLS LAST
        ) c
        WHERE e.id = c.employee_id
        """,
    )


def _move_country_code(env):
    """Move l10n_au_country_code -> l10n_au_work_country_id to the employee."""
    legacy_col = _get_contract_legacy("l10n_au_country_code")
    openupgrade.logged_query(
        env.cr,
        f"""
        UPDATE hr_employee e
        SET l10n_au_work_country_id = c.{legacy_col}
        FROM (
            SELECT DISTINCT ON (employee_id)
                employee_id, {legacy_col}
            FROM hr_contract
            WHERE {legacy_col} IS NOT NULL
            ORDER BY employee_id,
                CASE WHEN state = 'open' THEN 0 ELSE 1 END,
                date_start DESC NULLS LAST
        ) c
        WHERE e.id = c.employee_id
        """,
    )


def _split_tax_treatment_option(env):
    """Split l10n_au_tax_treatment_option from contract into 3 employee fields.

    v17: Single Selection on hr.contract with options D,P,C,O,S,M,I
    v18: Split into 3 fields on hr.employee based on tax_treatment_category:
      - l10n_au_tax_treatment_option_actor (for category A): options D,P
      - l10n_au_tax_treatment_option_voluntary (for category V): options C,O
      - l10n_au_tax_treatment_option_seniors (for category S): options S,M,I

    The legacy column may not exist if it was a non-stored compute with no data.
    """
    legacy_option = _get_contract_legacy("l10n_au_tax_treatment_option")
    legacy_category = openupgrade.get_legacy_name("l10n_au_tax_treatment_category")
    if not openupgrade.column_exists(env.cr, "hr_contract", legacy_option):
        return
    openupgrade.logged_query(
        env.cr,
        f"""
        WITH best_contract AS (
            SELECT DISTINCT ON (c.employee_id)
                c.employee_id,
                c.{legacy_option} AS option,
                st.{legacy_category} AS category
            FROM hr_contract c
            JOIN hr_payroll_structure_type st ON st.id = c.structure_type_id
            WHERE c.{legacy_option} IS NOT NULL
            ORDER BY c.employee_id,
                CASE WHEN c.state = 'open' THEN 0 ELSE 1 END,
                c.date_start DESC NULLS LAST
        )
        UPDATE hr_employee e
        SET l10n_au_tax_treatment_option_actor = CASE
                WHEN bc.category = 'A' AND bc.option IN ('D', 'P') THEN bc.option
                ELSE NULL
            END,
            l10n_au_tax_treatment_option_voluntary = CASE
                WHEN bc.category = 'V' AND bc.option IN ('C', 'O') THEN bc.option
                ELSE NULL
            END,
            l10n_au_tax_treatment_option_seniors = CASE
                WHEN bc.category = 'S' AND bc.option IN ('S', 'M', 'I') THEN bc.option
                ELSE NULL
            END
        FROM best_contract bc
        WHERE e.id = bc.employee_id
        """,
    )


def _move_tax_treatment_category(env):
    """Move l10n_au_tax_treatment_category from structure_type to employee.

    Uses the employee's best contract's structure_type_id.
    """
    legacy_category = openupgrade.get_legacy_name("l10n_au_tax_treatment_category")
    openupgrade.logged_query(
        env.cr,
        f"""
        UPDATE hr_employee e
        SET l10n_au_tax_treatment_category = st.{legacy_category}
        FROM (
            SELECT DISTINCT ON (c.employee_id)
                c.employee_id, c.structure_type_id
            FROM hr_contract c
            WHERE c.structure_type_id IS NOT NULL
            ORDER BY c.employee_id,
                CASE WHEN c.state = 'open' THEN 0 ELSE 1 END,
                c.date_start DESC NULLS LAST
        ) bc
        JOIN hr_payroll_structure_type st ON st.id = bc.structure_type_id
        WHERE e.id = bc.employee_id
        AND st.{legacy_category} IS NOT NULL
        """,
    )


_DROPPED_STRUCTURES = (
    "hr_payroll_structure_au_no_tfn",
    "hr_payroll_structure_au_whm",
    "hr_payroll_structure_au_senior",
    "hr_payroll_structure_au_lumpsum",
    "hr_payroll_structure_au_actor",
    "hr_payroll_structure_au_actor_promotional",
    "hr_payroll_structure_au_horticulture",
    "hr_payroll_structure_au_return_to_work",
    "hr_payroll_structure_au_termination",
)

_DROPPED_TYPES = (
    "structure_type_schedule_2",
    "structure_type_schedule_3",
    "structure_type_schedule_4",
    "structure_type_schedule_5",
    "structure_type_schedule_9",
    "structure_type_schedule_11_and_7",
    "structure_type_schedule_15",
    "structure_type_no_tfn",
)

_DROPPED_REGULAR_RULES = ("l10n_au_allowance_withholding_structure_1",)

_DROPPED_CATEGORIES = (
    "rule_category_etp_gross",
    "rule_category_etp_withhold",
    "rule_category_leave_base",
    "rule_category_leave_withhold",
)


def _module_ids(env, model, names):
    """Ids of the records behind xmlids of this module."""
    env.cr.execute(
        """
        SELECT res_id FROM ir_model_data
        WHERE module = 'l10n_au_hr_payroll' AND model = %s AND name IN %s
        """,
        (model, tuple(names)),
    )
    return tuple(res_id for (res_id,) in env.cr.fetchall())


def _keep_dropped_structures_apart(env):
    """Retire the nine 17.0 structures 18.0 drops, without merging their rules.

    18.0 pays every Australian employee through one structure and one
    structure type (the 17.0 schedules are employee fields now, moved above).
    The dropped structures each carry a full rule set (WITHHOLD, SUPER, ...,
    and the BASIC/GROSS/NET copies every structure gets on creation, which
    have no xmlid), so moving their rules into the regular structure would
    run the same codes several times on every new payslip. Instead:

    - contracts of a dropped structure type move to the 18.0 type, which pays
      through the regular structure;
    - the dropped structures move to that type too and are archived with all
      their rules, custom ones included, and their xmlids stop being updated,
      so historical payslips keep their structure and every line its rule;
      the dropped types, no longer used, are removed by the update;
    - a 17.0 regular rule 18.0 drops that payslip lines use is archived and
      kept the same way (an unused one is removed by the update);
    - a 17.0 rule category 18.0 drops (the termination ones) stays while a
      kept rule uses it, its xmlid no longer updated.

    Runs after the moves of the employee fields, which read the 17.0 type of
    the contracts. A second run changes nothing.
    """
    cr = env.cr
    target_type = env.ref("l10n_au_hr_payroll.structure_type_schedule_1").id
    types = _module_ids(env, "hr.payroll.structure.type", _DROPPED_TYPES)
    if types:
        openupgrade.logged_query(
            cr,
            """
            UPDATE hr_contract SET structure_type_id = %s
            WHERE structure_type_id IN %s
            """,
            (target_type, types),
        )
    structures = _module_ids(env, "hr.payroll.structure", _DROPPED_STRUCTURES)
    if structures:
        openupgrade.logged_query(
            cr,
            """
            UPDATE hr_payroll_structure SET type_id = %s, active = false
            WHERE id IN %s
            """,
            (target_type, structures),
        )
        openupgrade.logged_query(
            cr,
            "UPDATE hr_salary_rule SET active = false WHERE struct_id IN %s",
            (structures,),
        )
        openupgrade.logged_query(
            cr,
            """
            UPDATE ir_model_data SET noupdate = true
            WHERE module = 'l10n_au_hr_payroll' AND NOT coalesce(noupdate, false)
            AND (
                (model = 'hr.payroll.structure' AND res_id IN %(structures)s)
                OR (model = 'hr.salary.rule' AND res_id IN (
                    SELECT id FROM hr_salary_rule WHERE struct_id IN %(structures)s
                ))
            )
            """,
            {"structures": structures},
        )
    rules = _module_ids(env, "hr.salary.rule", _DROPPED_REGULAR_RULES)
    if rules:
        openupgrade.logged_query(
            cr,
            """
            UPDATE hr_salary_rule rule SET active = false
            WHERE rule.id IN %s AND EXISTS (
                SELECT 1 FROM hr_payslip_line line WHERE line.salary_rule_id = rule.id
            )
            """,
            (rules,),
        )
        openupgrade.logged_query(
            cr,
            """
            UPDATE ir_model_data data SET noupdate = true
            FROM hr_salary_rule rule
            WHERE data.module = 'l10n_au_hr_payroll' AND data.model = 'hr.salary.rule'
            AND data.res_id = rule.id AND rule.id IN %s AND NOT rule.active
            AND NOT coalesce(data.noupdate, false)
            """,
            (rules,),
        )
    categories = _module_ids(env, "hr.salary.rule.category", _DROPPED_CATEGORIES)
    if categories:
        openupgrade.logged_query(
            cr,
            """
            UPDATE ir_model_data data SET noupdate = true
            WHERE data.module = 'l10n_au_hr_payroll'
            AND data.model = 'hr.salary.rule.category'
            AND data.res_id IN %s AND NOT coalesce(data.noupdate, false)
            AND EXISTS (
                SELECT 1 FROM hr_salary_rule rule WHERE rule.category_id = data.res_id
            )
            """,
            (categories,),
        )
    env["hr.contract"].invalidate_model(["structure_type_id"])
    env["hr.payroll.structure"].invalidate_model(["type_id", "active"])
    env["hr.salary.rule"].invalidate_model(["active"])


@openupgrade.migrate()
def migrate(env, version):
    _move_withholding_variation(env)
    _move_employment_basis_code(env)
    _move_country_code(env)
    _split_tax_treatment_option(env)
    _move_tax_treatment_category(env)
    _keep_dropped_structures_apart(env)
