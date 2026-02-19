# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _move_sdd_mandate_to_payment(env):
    """Move sdd_mandate_id from account_move to account_payment.

    In 17.0: sdd_mandate_id lived on account.move, accessible on payments
    through _inherits.
    In 18.0: account.payment has its own sdd_mandate_id column, and
    account.move has a related (not stored) field.
    """
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE account_payment
        ADD COLUMN IF NOT EXISTS sdd_mandate_id integer
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_payment ap
        SET sdd_mandate_id = am.sdd_mandate_id
        FROM account_move am
        WHERE ap.move_id = am.id
        AND am.sdd_mandate_id IS NOT NULL
        AND ap.sdd_mandate_id IS NULL
        """,
    )


def _set_pre_notification_defaults(env):
    """Set pre_notification_period default on existing sdd_mandate records.

    New required field in 18.0 with default=2.
    """
    if openupgrade.table_exists(env.cr, "sdd_mandate"):
        openupgrade.logged_query(
            env.cr,
            """
            ALTER TABLE sdd_mandate
            ADD COLUMN IF NOT EXISTS pre_notification_period integer
            """,
        )
        openupgrade.logged_query(
            env.cr,
            """
            UPDATE sdd_mandate
            SET pre_notification_period = 2
            WHERE pre_notification_period IS NULL
            """,
        )


@openupgrade.migrate()
def migrate(env, version):
    _move_sdd_mandate_to_payment(env)
    _set_pre_notification_defaults(env)
