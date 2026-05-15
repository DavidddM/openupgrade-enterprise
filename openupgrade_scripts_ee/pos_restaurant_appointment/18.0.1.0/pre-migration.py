# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade
from psycopg2 import sql

from odoo.upgrade.lib import relation

_logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    """Keep one appointment type per point of sale, the first active one.

    18.0 replaces the many2many ``pos.config.appointment_type_ids`` with the
    many2one ``appointment_type_id``. The column is added before the load and
    filled from the 17.0 relation (an active type first, then the lowest id);
    points of sale that had several types are listed in a warning. The
    relation table stays. A second run changes nothing.
    """
    table = relation.default_name("pos_config", "appointment_type")
    openupgrade.logged_query(
        env.cr,
        "ALTER TABLE pos_config ADD COLUMN IF NOT EXISTS appointment_type_id integer",
    )
    if not openupgrade.table_exists(env.cr, table):
        return
    openupgrade.logged_query(
        env.cr,
        sql.SQL(
            """
            UPDATE pos_config config
            SET appointment_type_id = chosen.appointment_type_id
            FROM (
                SELECT DISTINCT ON (rel.pos_config_id)
                    rel.pos_config_id, rel.appointment_type_id
                FROM {table} rel
                JOIN appointment_type atype ON atype.id = rel.appointment_type_id
                ORDER BY rel.pos_config_id, atype.active DESC, atype.id
            ) chosen
            WHERE chosen.pos_config_id = config.id
                AND config.appointment_type_id IS NULL
            """
        ).format(table=sql.Identifier(table)),
    )
    env.cr.execute(
        sql.SQL(
            """
            SELECT string_agg(
                format('%s kept %s of %s', config.id, config.appointment_type_id,
                    several.types),
                '; ' ORDER BY config.id)
            FROM pos_config config
            JOIN (
                SELECT pos_config_id,
                    string_agg(appointment_type_id::text, ','
                        ORDER BY appointment_type_id) AS types
                FROM {table}
                GROUP BY pos_config_id
                HAVING count(*) > 1
            ) several ON several.pos_config_id = config.id
            """
        ).format(table=sql.Identifier(table))
    )
    several = env.cr.fetchone()[0]
    if several:
        _logger.warning(
            "Points of sale with several 17.0 appointment types keep one"
            " (pos.config id, kept type, 17.0 types): %s",
            several,
        )
