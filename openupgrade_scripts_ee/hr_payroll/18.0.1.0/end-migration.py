# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

from odoo.upgrade.lib import payroll


@openupgrade.migrate()
def migrate(env, version):
    """Keep the payroll records 18.0 drops while 17.0 payslips use them.

    End-migrations run once every module's data is loaded and before the update
    deletes the records whose xmlid it no longer loaded, which is when the
    records 18.0 dropped are known.
    """
    payroll.keep_used_records(env)
