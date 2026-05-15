# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def _lines_without_account(env):
    """Return the SuperStream lines without member account, with their payee."""
    env.cr.execute(
        """
        SELECT line.id, line.employee_id, line.payee_id, slip.date_from
        FROM l10n_au_super_stream_line line
        JOIN hr_payslip slip ON slip.id = line.payslip_id
        WHERE line.super_account_id IS NULL AND line.payee_id IS NOT NULL
        ORDER BY line.id
        """
    )
    return env.cr.fetchall()


def _super_accounts_of_lines(env):
    """Give every 17.0 SuperStream line a member account at its payee fund.

    17.0 stored the payee fund of a line and copied the employee's current
    super account into it, empty when the employee had none; 18.0 requires the
    account and derives the payee from the account's fund. A line without
    account gets the employee's account at its payee fund (active first, then
    the latest, then the lowest id); when the employee has none there, an
    archived account at that fund, effective from the payslip start, keeps the
    payee 17.0 paid. Lines whose account belongs to another fund than their
    17.0 payee are listed in a warning. A second run finds no line to fill.
    """
    if not openupgrade.column_exists(env.cr, "l10n_au_super_stream_line", "payee_id"):
        return
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE l10n_au_super_stream_line line
        SET super_account_id = account.id
        FROM (
            SELECT DISTINCT ON (employee_id, fund_id) id, employee_id, fund_id
            FROM l10n_au_super_account
            ORDER BY employee_id, fund_id, account_active DESC,
                date_from DESC NULLS LAST, id
        ) account
        WHERE line.super_account_id IS NULL
            AND account.employee_id = line.employee_id
            AND account.fund_id = line.payee_id
        """,
    )
    created = {}
    for line_id, employee_id, fund_id, date_from in _lines_without_account(env):
        key = (employee_id, fund_id)
        if key not in created:
            created[key] = (
                env["l10n_au.super.account"]
                .create(
                    {
                        "employee_id": employee_id,
                        "fund_id": fund_id,
                        "date_from": date_from,
                        "account_active": False,
                    }
                )
                .id
            )
        env.cr.execute(
            "UPDATE l10n_au_super_stream_line SET super_account_id = %s WHERE id = %s",
            (created[key], line_id),
        )
    if created:
        _logger.info(
            "Archived super accounts created for SuperStream lines of employees"
            " without account at their payee fund: %s",
            sorted(created.values()),
        )
    env.cr.execute(
        """
        SELECT string_agg(line.id::text, ', ' ORDER BY line.id)
        FROM l10n_au_super_stream_line line
        JOIN l10n_au_super_account account ON account.id = line.super_account_id
        WHERE account.fund_id IS DISTINCT FROM line.payee_id
        """
    )
    mismatched = env.cr.fetchone()[0]
    if mismatched:
        _logger.warning(
            "SuperStream lines whose super account belongs to another fund than"
            " their 17.0 payee, which 18.0 now shows as payee: %s",
            mismatched,
        )


@openupgrade.migrate()
def migrate(env, version):
    _super_accounts_of_lines(env)
