# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_field_renames = [
    ("hr.payslip", "hr_payslip", "sepa_uetr", "iso20022_uetr"),
]


@openupgrade.migrate()
def migrate(env, version):
    """Keep the UETR of every paid payslip under its 18.0 name.

    The base pre-migration renamed hr_payroll_account_sepa to
    hr_payroll_account_iso20022; 18.0 renamed the payslip's unique end-to-end
    transaction reference from ``sepa_uetr`` to ``iso20022_uetr``, as
    account_iso20022 did for payments. A payslip without it gets a new
    reference at its next export, so the bank would see the same salary
    payment under two references.
    """
    openupgrade.rename_fields(env, _field_renames)
