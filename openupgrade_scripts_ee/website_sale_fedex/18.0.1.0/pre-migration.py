# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _convert_fedex_radius_to_km(env):
    """Convert fedex_locations_radius_value from the old unit to km.

    In 17.0 the unit was user-editable (km or miles, default=km with value=15).
    In 18.0 the unit is a stored compute that always resolves to km or miles.
    We convert every carrier's value to km so the new compute starts from a
    correct base.
    """
    if not openupgrade.column_exists(
        env.cr, "delivery_carrier", "fedex_locations_radius_unit"
    ):
        return
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE delivery_carrier
        SET fedex_locations_radius_value = GREATEST(1, ROUND(
            fedex_locations_radius_value / src_uom.factor * dst_uom.factor
        )::integer)
        FROM uom_uom AS src_uom, uom_uom AS dst_uom
        WHERE delivery_carrier.fedex_locations_radius_unit = src_uom.id
          AND dst_uom.id = (
              SELECT res_id FROM ir_model_data
              WHERE module = 'uom' AND name = 'product_uom_km'
          )
          AND delivery_carrier.fedex_locations_radius_unit != dst_uom.id
          AND delivery_carrier.fedex_locations_radius_unit IS NOT NULL
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _convert_fedex_radius_to_km(env)
