# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _setup_deferred_accounts(env):
    """Give the SKR03/SKR04 companies their deferred accounts where unset."""
    for company in env["res.company"].search([]):
        if company.chart_template in ("de_skr03", "de_skr04"):
            if company.chart_template == "de_skr03":
                expense_account = env.ref(
                    f"account.{company.id}_account_0980", raise_if_not_found=False
                )
                revenue_account = env.ref(
                    f"account.{company.id}_account_0990", raise_if_not_found=False
                )
            else:
                expense_account = env.ref(
                    f"account.{company.id}_chart_skr04_1900", raise_if_not_found=False
                )
                revenue_account = env.ref(
                    f"account.{company.id}_chart_skr04_3900", raise_if_not_found=False
                )
            if expense_account and not company.deferred_expense_account_id:
                company.deferred_expense_account_id = expense_account
            if revenue_account and not company.deferred_revenue_account_id:
                company.deferred_revenue_account_id = revenue_account


@openupgrade.migrate()
def migrate(env, version):
    """Set the DATEV deferred accounts of the SKR03/SKR04 companies.

    The DATEV numbers of companies and partners become company-dependent jsonb
    values in the shared step ``odoo.upgrade.lib.company_dependent``, run by
    the base end-migration of this repository: the company numbers from
    ir_property, the partner identifiers from the legacy columns the
    pre-migration keeps.
    """
    _setup_deferred_accounts(env)
