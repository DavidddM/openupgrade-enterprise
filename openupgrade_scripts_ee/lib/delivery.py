# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Pick-up point search radius of delivery carriers, whose unit 18.0 computes."""

from openupgradelib import openupgrade
from psycopg2 import sql


def set_radius_unit(env, value_column, unit_column, missing_unit):
    """Express a carrier radius in the unit 18.0 gives it.

    17.0 lets each carrier choose the radius unit; 18.0 makes the unit a
    stored compute without dependencies that returns miles when the
    ``product.volume_in_cubic_feet`` parameter is '1' (imperial units) and
    kilometres otherwise. The column exists in 17.0, so the module load
    neither recomputes it nor converts the value. Every value is converted
    from its 17.0 unit into that unit (rounded half up to an integer, at
    least 1) and the unit is set; a carrier without unit is read in
    ``missing_unit`` (xmlid), as 17.0 did. A second run changes nothing.
    """
    cr = env.cr
    if not openupgrade.column_exists(cr, "delivery_carrier", unit_column):
        return
    cr.execute(
        "SELECT value FROM ir_config_parameter WHERE key = %s",
        ("product.volume_in_cubic_feet",),
    )
    row = cr.fetchone()
    target = env.ref(
        "uom.product_uom_mile" if row and row[0] == "1" else "uom.product_uom_km"
    )
    openupgrade.logged_query(
        cr,
        sql.SQL(
            """
            UPDATE delivery_carrier carrier
            SET {value} = GREATEST(
                    1, ROUND(carrier.{value} / source.factor * target.factor)
                )::integer,
                {unit} = target.id
            FROM uom_uom source, uom_uom target
            WHERE source.id = COALESCE(carrier.{unit}, %(missing)s)
                AND target.id = %(target)s
                AND carrier.{unit} IS DISTINCT FROM target.id
            """
        ).format(value=sql.Identifier(value_column), unit=sql.Identifier(unit_column)),
        {"missing": env.ref(missing_unit).id, "target": target.id},
    )
