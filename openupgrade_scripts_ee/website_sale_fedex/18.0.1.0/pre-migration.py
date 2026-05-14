# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

from odoo.upgrade.lib import delivery


@openupgrade.migrate()
def migrate(env, version):
    """Express the FedEx pick-up radius in the 18.0 unit (17.0 default: km)."""
    delivery.set_radius_unit(
        env,
        "fedex_locations_radius_value",
        "fedex_locations_radius_unit",
        "uom.product_uom_km",
    )
