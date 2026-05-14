# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade
from psycopg2 import sql

from odoo.upgrade.lib import relation

_logger = logging.getLogger(__name__)


def _customs_regimes_of_pickings(env):
    """Carry the single 17.0 customs regime of a picking into its 18.0 regimes.

    l10n_mx_edi_stock_extended_30 stored one regime per picking; its 3.1
    successor added the many2many 18.0 keeps and filled it from the single
    regime only when it got installed (its post_init_hook). A picking of a
    database that never ran 3.1 gets its regime here; a picking that already
    has regimes keeps exactly those. A second run adds nothing.
    """
    column = "l10n_mx_edi_customs_regime_id"
    if not openupgrade.column_exists(env.cr, "stock_picking", column):
        return
    table = relation.default_name("stock_picking", "l10n_mx_edi_customs_regime")
    openupgrade.logged_query(
        env.cr,
        sql.SQL(
            """
            INSERT INTO {table} (stock_picking_id, l10n_mx_edi_customs_regime_id)
            SELECT sp.id, sp.{column}
            FROM stock_picking sp
            WHERE sp.{column} IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM {table} rel WHERE rel.stock_picking_id = sp.id
                )
            """
        ).format(table=sql.Identifier(table), column=sql.Identifier(column)),
    )


def _hazardous_material_codes(env):
    """Turn the typed 17.0 hazardous material code into the 18.0 catalog entry.

    l10n_mx_edi_stock_extended kept the SAT designation code of a product as
    text, '0' meaning not hazardous; 18.0 links the product to the
    l10n_mx_edi.hazardous.material catalog it loads. Products whose code has
    no catalog entry keep the text in its column and are listed in a warning.
    """
    column = "l10n_mx_edi_hazardous_material_code"
    if not openupgrade.column_exists(env.cr, "product_template", column):
        return
    openupgrade.logged_query(
        env.cr,
        sql.SQL(
            """
            UPDATE product_template pt
            SET l10n_mx_edi_hazardous_material_code_id = hm.id
            FROM l10n_mx_edi_hazardous_material hm
            WHERE hm.code = btrim(pt.{column})
                AND pt.l10n_mx_edi_hazardous_material_code_id IS NULL
            """
        ).format(column=sql.Identifier(column)),
    )
    env.cr.execute(
        sql.SQL(
            """
            SELECT string_agg(pt.id || ':' || pt.{column}, ', ' ORDER BY pt.id)
            FROM product_template pt
            WHERE btrim(coalesce(pt.{column}, '')) NOT IN ('', '0')
                AND pt.l10n_mx_edi_hazardous_material_code_id IS NULL
            """
        ).format(column=sql.Identifier(column))
    )
    unmatched = env.cr.fetchone()[0]
    if unmatched:
        _logger.warning(
            "Products whose 17.0 hazardous material code is not in the 18.0"
            " catalog, left without code (product template id:code): %s",
            unmatched,
        )


def _hazard_package_types(env):
    """Put back the 17.0 packaging type of hazardous products the load emptied.

    The pre-migration kept it in a legacy column; a product whose 18.0 value
    is empty gets its 17.0 one back.
    """
    legacy = openupgrade.get_legacy_name("l10n_mx_edi_hazard_package_type")
    if not openupgrade.column_exists(env.cr, "product_template", legacy):
        return
    openupgrade.logged_query(
        env.cr,
        sql.SQL(
            """
            UPDATE product_template
            SET l10n_mx_edi_hazard_package_type = {legacy}
            WHERE {legacy} IS NOT NULL AND l10n_mx_edi_hazard_package_type IS NULL
            """
        ).format(legacy=sql.Identifier(legacy)),
    )


@openupgrade.migrate()
def migrate(env, version):
    _customs_regimes_of_pickings(env)
    _hazardous_material_codes(env)
    _hazard_package_types(env)
