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
    """Move l10n_au_country_code -> l10n_au_work_country_id from contract to employee."""
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
    """
    legacy_option = _get_contract_legacy("l10n_au_tax_treatment_option")
    legacy_category = openupgrade.get_legacy_name("l10n_au_tax_treatment_category")
    # Column may not exist if it was a non-stored compute with no data
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


@openupgrade.migrate()
def migrate(env, version):
    _move_withholding_variation(env)
    _move_employment_basis_code(env)
    _move_country_code(env)
    _split_tax_treatment_option(env)
    _move_tax_treatment_category(env)
