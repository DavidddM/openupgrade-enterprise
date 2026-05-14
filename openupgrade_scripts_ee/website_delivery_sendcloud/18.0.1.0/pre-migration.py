# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

from odoo.upgrade.lib import delivery


@openupgrade.migrate()
def migrate(env, version):
    """Express the Sendcloud pick-up radius in the 18.0 unit (17.0 default: m)."""
    delivery.set_radius_unit(
        env,
        "sendcloud_locations_radius_value",
        "sendcloud_locations_radius_unit",
        "uom.product_uom_meter",
    )
