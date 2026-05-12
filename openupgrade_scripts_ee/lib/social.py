# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Per-network message and images of social posts, new in 18.0."""

from openupgradelib import openupgrade
from psycopg2 import sql

from odoo.upgrade.lib import relation

TABLES = (
    ("social_post_template", "template_%s_image_ids_rel"),
    ("social_post", "%s_image_ids_rel"),
)


def prefill_network(env, network):
    """Give a network's 18.0 message and images the 17.0 shared content.

    18.0 adds ``<network>_message`` and ``<network>_image_ids`` to social post
    templates and posts, stored computes that copy ``message`` and
    ``image_ids`` while a post is not split per network, which no 17.0 post
    is. 17.0 keeps ``image_ids`` in the default relation of each model
    (``ir_attachment_social_post_template_rel``,
    ``ir_attachment_social_post_rel``); 18.0 keeps the network images in
    ``template_<network>_image_ids_rel`` and ``<network>_image_ids_rel``.
    Columns and tables made here are left alone by the module load, which
    neither fills nor recomputes them. A second run changes nothing.
    """
    cr = env.cr
    message = "%s_message" % network
    for table, target in TABLES:
        if not openupgrade.column_exists(cr, table, message):
            openupgrade.logged_query(
                cr,
                sql.SQL("ALTER TABLE {} ADD COLUMN {} text").format(
                    sql.Identifier(table), sql.Identifier(message)
                ),
            )
            openupgrade.logged_query(
                cr,
                sql.SQL("UPDATE {} SET {} = message WHERE message IS NOT NULL").format(
                    sql.Identifier(table), sql.Identifier(message)
                ),
            )
        relation.copy_pairs(
            cr,
            relation.default_name(table, "ir_attachment"),
            target % network,
            "%s_id" % table,
            "ir_attachment_id",
        )
