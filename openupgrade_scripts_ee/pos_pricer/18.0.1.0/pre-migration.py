# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade
from psycopg2 import sql

from odoo.upgrade.lib import schema

_logger = logging.getLogger(__name__)


def _store_on_variants(env):
    """Give every variant the Pricer store of its template and queue it for Pricer.

    18.0 moves the store and the update flag from product.template to
    product.product. 17.0 sent each template to Pricer under the template id;
    18.0 sends variants under their own id, so every variant of a template
    that had a store is flagged to be created in Pricer by the next sync.
    """
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE product_product
            ADD COLUMN IF NOT EXISTS pricer_store_id integer,
            ADD COLUMN IF NOT EXISTS pricer_product_to_create_or_update boolean
        """,
    )
    if not openupgrade.column_exists(env.cr, "product_template", "pricer_store_id"):
        return
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE product_product variant
        SET pricer_store_id = template.pricer_store_id,
            pricer_product_to_create_or_update = TRUE
        FROM product_template template
        WHERE variant.product_tmpl_id = template.id
            AND template.pricer_store_id IS NOT NULL
            AND variant.pricer_store_id IS NULL
        """,
    )


def _tags_on_variants(env):
    """Point every Pricer tag at a variant of its 17.0 template.

    ``pricer.tag.product_id`` changes comodel from product.template to
    product.product. The 17.0 template ids move to a legacy column without
    foreign key before the load, which would otherwise add the new foreign key
    against template ids. A tag gets the first variant of its template (active
    first, then the lowest id), the variant 17.0 showed for a single-variant
    template, and is flagged to be linked again in Pricer, where its item now
    has the variant id. A second run maps from the legacy column again and
    changes nothing.
    """
    legacy = schema.detach_column(env.cr, "pricer_tag", "product_id")
    if not openupgrade.column_exists(env.cr, "pricer_tag", legacy):
        return
    openupgrade.logged_query(
        env.cr, "ALTER TABLE pricer_tag ADD COLUMN IF NOT EXISTS product_id integer"
    )
    openupgrade.logged_query(
        env.cr,
        sql.SQL(
            """
            UPDATE pricer_tag tag
            SET product_id = variant.id, pricer_product_to_link = TRUE
            FROM (
                SELECT DISTINCT ON (product_tmpl_id) id, product_tmpl_id
                FROM product_product
                ORDER BY product_tmpl_id, active DESC, id
            ) variant
            WHERE variant.product_tmpl_id = tag.{legacy}
                AND tag.product_id IS DISTINCT FROM variant.id
            """
        ).format(legacy=sql.Identifier(legacy)),
    )
    env.cr.execute(
        sql.SQL(
            """
            SELECT string_agg(tag.id::text, ', ' ORDER BY tag.id)
            FROM pricer_tag tag
            WHERE tag.product_id IS NULL AND tag.{legacy} IS NOT NULL
            """
        ).format(legacy=sql.Identifier(legacy))
    )
    orphans = env.cr.fetchone()[0]
    if orphans:
        _logger.warning("Pricer tags whose template has no variant: %s", orphans)


@openupgrade.migrate()
def migrate(env, version):
    _store_on_variants(env)
    _tags_on_variants(env)
