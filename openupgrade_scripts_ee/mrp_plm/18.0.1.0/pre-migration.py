# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade
from psycopg2 import sql

from odoo.upgrade.lib import schema

_logger = logging.getLogger(__name__)


def _remap_displayed_image(env):
    """Point mrp.eco.displayed_image_id at product.document before the load.

    The field's comodel changes from mrp.document to product.document. The
    community mrp post-migration, which runs before this module, copies every
    mrp_document row into product_document with new ids and keeps the old id
    in a link column. The 17.0 ids move to a legacy column without foreign key
    and the field is refilled through that link here, so the foreign key the
    module load adds holds and an mrp_document id that happens to exist in
    product_document no longer selects the wrong document. A second run
    remaps from the legacy column again and gives the same result.
    """
    link = openupgrade.get_legacy_name("mrp_document_id")
    if not openupgrade.column_exists(env.cr, "product_document", link):
        return
    legacy = schema.detach_column(env.cr, "mrp_eco", "displayed_image_id")
    if not openupgrade.column_exists(env.cr, "mrp_eco", legacy):
        return
    openupgrade.logged_query(
        env.cr,
        "ALTER TABLE mrp_eco ADD COLUMN IF NOT EXISTS displayed_image_id integer",
    )
    openupgrade.logged_query(
        env.cr,
        sql.SQL(
            """
            UPDATE mrp_eco eco
            SET displayed_image_id = pd.id
            FROM product_document pd
            WHERE pd.{link} = eco.{legacy}
                AND eco.displayed_image_id IS DISTINCT FROM pd.id
            """
        ).format(link=sql.Identifier(link), legacy=sql.Identifier(legacy)),
    )
    env.cr.execute(
        sql.SQL(
            """
            SELECT array_agg(eco.id ORDER BY eco.id)
            FROM mrp_eco eco
            WHERE eco.{legacy} IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM product_document pd WHERE pd.{link} = eco.{legacy}
                )
            """
        ).format(link=sql.Identifier(link), legacy=sql.Identifier(legacy))
    )
    missing = env.cr.fetchone()[0]
    if missing:
        _logger.warning(
            "mrp.eco %s: displayed image has no product.document copy, cleared",
            missing,
        )
        openupgrade.logged_query(
            env.cr,
            "UPDATE mrp_eco SET displayed_image_id = NULL WHERE id IN %s",
            (tuple(missing),),
        )


@openupgrade.migrate()
def migrate(env, version):
    _remap_displayed_image(env)
