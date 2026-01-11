# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _fill_deferred_revenue_fields(env):
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE res_company
        SET deferred_revenue_journal_id = deferred_expense_journal_id
        WHERE deferred_revenue_journal_id IS NULL
            AND deferred_expense_journal_id IS NOT NULL
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE res_company
        SET deferred_revenue_amount_computation_method =
            deferred_expense_amount_computation_method
        WHERE deferred_revenue_amount_computation_method IS NULL
            AND deferred_expense_amount_computation_method IS NOT NULL
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _fill_deferred_revenue_fields(env)
