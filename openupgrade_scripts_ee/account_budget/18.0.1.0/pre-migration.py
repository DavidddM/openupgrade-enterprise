# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_model_renames = [
    ("crossovered.budget", "budget.analytic"),
    ("crossovered.budget.lines", "budget.line"),
]

_table_renames = [
    ("crossovered_budget", "budget_analytic"),
    ("crossovered_budget_lines", "budget_line"),
]

_column_renames = {
    "budget_line": [
        ("crossovered_budget_id", "budget_analytic_id"),
        ("planned_amount", "budget_amount"),
    ],
}


def _map_budget_states(env):
    """Map old budget state values to 18.0 equivalents.

    confirm -> confirmed, cancel -> canceled, validate -> done
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE budget_analytic
        SET state = CASE
            WHEN state = 'confirm' THEN 'confirmed'
            WHEN state = 'cancel' THEN 'canceled'
            WHEN state = 'validate' THEN 'done'
            ELSE state
        END
        WHERE state IN ('confirm', 'cancel', 'validate')
        """,
    )


def _add_budget_line_defaults(env):
    """Add new required columns on budget_line with defaults."""
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE budget_line
        ADD COLUMN IF NOT EXISTS budget_type varchar,
        ADD COLUMN IF NOT EXISTS sequence integer
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE budget_line
        SET budget_type = COALESCE(budget_type, 'expense'),
            sequence = COALESCE(sequence, 10)
        """,
    )


def _fill_budget_analytic_required_dates(env):
    """Ensure date_from and date_to are set on budget_analytic (required in 18.0)."""
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE budget_analytic
        SET date_from = COALESCE(date_from, create_date::date, '2024-01-01'::date),
            date_to = COALESCE(date_to, create_date::date + interval '1 year',
                               '2024-12-31'::date)
        WHERE date_from IS NULL OR date_to IS NULL
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_models(env.cr, _model_renames)
    openupgrade.rename_tables(env.cr, _table_renames)
    openupgrade.rename_columns(env.cr, _column_renames)
    _map_budget_states(env)
    _add_budget_line_defaults(env)
    _fill_budget_analytic_required_dates(env)
