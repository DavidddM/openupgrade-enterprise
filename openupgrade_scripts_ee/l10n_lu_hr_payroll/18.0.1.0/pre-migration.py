# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_field_renames = [
    ("hr.employee", "hr_employee", "l10n_lu_tax_card_number", "l10n_lu_tax_id_number"),
]

_xmlid_renames = [
    (
        "l10n_lu_hr_payroll.rule_parameter_cissm_max_amount_2023",
        "l10n_lu_hr_payroll.rule_parameter_cissm_max_amount_2019",
    ),
]

_DAYS_PER_MONTH = 25


def _vehicle_benefit(env):
    """Carry the 17.0 vehicle package of a contract into the 18.0 vehicle benefit.

    17.0 declared the company car with ``l10n_lu_atn_transport`` (ATN, the
    benefit in kind, "the amount includes VAT") and split it into the
    BIK_TRANSPORT_NO_VAT and BIK_TRANSPORT_VAT rules; 18.0 has
    ``l10n_lu_bik_vehicle`` with ``l10n_lu_bik_vehicle_vat_included`` (default
    true) and the same split in BIK_VEHICLE_NO_VAT and BIK_VEHICLE_VAT. The
    column is added before the load so it keeps the 17.0 amounts.
    """
    if not openupgrade.column_exists(env.cr, "hr_contract", "l10n_lu_atn_transport"):
        return
    openupgrade.logged_query(
        env.cr,
        "ALTER TABLE hr_contract ADD COLUMN IF NOT EXISTS l10n_lu_bik_vehicle numeric",
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE hr_contract
        SET l10n_lu_bik_vehicle = l10n_lu_atn_transport
        WHERE coalesce(l10n_lu_atn_transport, 0) <> 0
            AND coalesce(l10n_lu_bik_vehicle, 0) = 0
        """,
    )


def _travel_expenses(env):
    """Turn the 17.0 monthly travel expense deduction into the 18.0 daily one.

    17.0 deducted ``l10n_lu_travel_expense`` per month (rule TRANS_FEES,
    "Transport Fees"); 18.0 deducts ``l10n_lu_deduction_fd_daily`` per taxable
    day (rule FD, "Transport Fees") and shows it per month as the daily amount
    times the ``l10n_lu_days_per_month`` rule parameter, 25 since 2017. The
    column is added before the load, so the payslips 18.0 computes at load see
    the daily amount.
    """
    if not openupgrade.column_exists(env.cr, "hr_employee", "l10n_lu_travel_expense"):
        return
    openupgrade.logged_query(
        env.cr,
        "ALTER TABLE hr_employee"
        " ADD COLUMN IF NOT EXISTS l10n_lu_deduction_fd_daily numeric",
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE hr_employee
        SET l10n_lu_deduction_fd_daily = l10n_lu_travel_expense::numeric / %s
        WHERE coalesce(l10n_lu_travel_expense, 0) <> 0
            AND coalesce(l10n_lu_deduction_fd_daily, 0) = 0
        """,
        (_DAYS_PER_MONTH,),
    )


@openupgrade.migrate()
def migrate(env, version):
    """Keep the Luxembourg employee and contract data 18.0 renamed or reshaped.

    The tax card number becomes the tax identification number: the same demo
    employee carries the same number under both names, and 18.0 prints and
    declares it where 17.0 printed the tax card number. The 17.0 CISSM ceiling
    value named 2023 is dated 2019-01-01; 18.0 ships that value as
    ``rule_parameter_cissm_max_amount_2019``, and the unique (parameter, date)
    of rule parameter values would abort the load if the 17.0 record kept its
    name.
    """
    openupgrade.rename_xmlids(env.cr, _xmlid_renames)
    openupgrade.rename_fields(env, _field_renames)
    _vehicle_benefit(env)
    _travel_expenses(env)
