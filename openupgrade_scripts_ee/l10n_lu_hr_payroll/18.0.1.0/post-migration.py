# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _closed_payslip_tax_ids(env):
    """Print the employee's tax identification number on 17.0 closed payslips.

    18.0 stores the number on each payslip and fills it only while the payslip
    is open; 17.0 printed the employee's number on every payslip. Closed
    Luxembourg payslips without number take their employee's.
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE hr_payslip slip
        SET l10n_lu_tax_id_number = employee.l10n_lu_tax_id_number
        FROM hr_employee employee, res_company company, res_partner partner,
            res_country country
        WHERE employee.id = slip.employee_id
            AND company.id = slip.company_id
            AND partner.id = company.partner_id
            AND country.id = partner.country_id
            AND country.code = 'LU'
            AND slip.state IN ('done', 'paid')
            AND slip.l10n_lu_tax_id_number IS NULL
            AND employee.l10n_lu_tax_id_number IS NOT NULL
        """,
    )


def _activate_total_allowances(env):
    """Activate the total allowances rule, which 17.0 shipped archived.

    17.0 archived ``l10n_lu_employees_total_allowance`` (ALW_TOTAL); 18.0
    reuses the record as TOTAL_ALLOWANCES, active, and takes the tax
    deductions (transport fees FD and the other daily deductions) off the
    taxable amount through its category. The update does not reset a field
    the 18.0 data leaves out, so without this the rule stays archived and
    the deductions no longer lower the withholding tax.
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE hr_salary_rule rule SET active = true
        FROM ir_model_data data
        WHERE data.module = 'l10n_lu_hr_payroll'
            AND data.name = 'l10n_lu_employees_total_allowance'
            AND data.model = 'hr.salary.rule'
            AND rule.id = data.res_id
            AND NOT rule.active
        """,
    )
    env["hr.salary.rule"].invalidate_model(["active"])


@openupgrade.migrate()
def migrate(env, version):
    """Carry the Luxembourg payslip data and rules 18.0 changed in place."""
    _closed_payslip_tax_ids(env)
    _activate_total_allowances(env)
