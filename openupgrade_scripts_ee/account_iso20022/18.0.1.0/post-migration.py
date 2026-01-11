# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _fill_iso20022_charge_bearer(env):
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_batch_payment
        SET iso20022_charge_bearer = 'SLEV'
        WHERE iso20022_charge_bearer IS NULL
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _fill_iso20022_charge_bearer(env)
