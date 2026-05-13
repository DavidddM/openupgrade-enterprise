# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade
from psycopg2 import sql

_logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    """Put the 17.0 analytic account of each budget line in its plan column.

    An 18.0 budget line keeps an account in the column of the account's root
    plan: ``account_id`` for the project plan, ``x_plan<id>_id`` for the other
    roots. The analytic end-migration creates those columns on budget lines
    (the account_budget install hook that does it does not run on update),
    and end-migrations run in dependency order, so they exist here. Lines that
    already have an account in that column are left alone.
    """
    cr = env.cr
    legacy = openupgrade.get_legacy_name("analytic_account_id")
    if not openupgrade.column_exists(cr, "budget_line", legacy):
        return
    cr.execute(
        sql.SQL(
            """
            SELECT DISTINCT account.root_plan_id
            FROM budget_line line
            JOIN account_analytic_account account ON account.id = line.{legacy}
            """
        ).format(legacy=sql.Identifier(legacy))
    )
    plan_ids = [plan_id for (plan_id,) in cr.fetchall() if plan_id]
    for plan in env["account.analytic.plan"].browse(plan_ids):
        column = plan._column_name()
        if not openupgrade.column_exists(cr, "budget_line", column):
            _logger.warning(
                "Budget lines on analytic plan %s keep their account in %s only:"
                " column %s is missing",
                plan.id,
                legacy,
                column,
            )
            continue
        openupgrade.logged_query(
            cr,
            sql.SQL(
                """
                UPDATE budget_line line
                SET {column} = line.{legacy}
                FROM account_analytic_account account
                WHERE account.id = line.{legacy}
                    AND account.root_plan_id = %s
                    AND line.{column} IS NULL
                """
            ).format(column=sql.Identifier(column), legacy=sql.Identifier(legacy)),
            (plan.id,),
        )
