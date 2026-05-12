# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

from odoo.upgrade.lib import company_dependent


@openupgrade.migrate()
def migrate(env, version):
    """Convert the enterprise company-dependent fields before ir.property goes.

    End-migrations run after every module is loaded, base first, and the
    versions of one stage in ascending order, so this script runs before the
    base 18.0.1.3 end-migration that removes the ir.property model.
    """
    company_dependent.convert_all(env)
