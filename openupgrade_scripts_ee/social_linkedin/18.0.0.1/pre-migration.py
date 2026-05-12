# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

from odoo.upgrade.lib import social


@openupgrade.migrate()
def migrate(env, version):
    """Give the LinkedIn message and images the 17.0 shared post content."""
    social.prefill_network(env, "linkedin")
