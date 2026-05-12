# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Many2many relation tables whose content moves to another relation in 18.0."""

from openupgradelib import openupgrade
from psycopg2 import sql


def default_name(table1, table2):
    """Relation table of a many2many field declared without ``relation=``.

    The ORM sorts the two model tables and joins them, so the name does not
    depend on which side declares the field.
    """
    return "%s_%s_rel" % tuple(sorted((table1, table2)))


def copy_pairs(cr, source, target, column1, column2):
    """Copy the pairs of ``source`` into ``target``, created as the ORM would.

    ``target`` gets both columns NOT NULL, the pair as primary key, the
    reverse index and the table comment of an ORM relation; the module load
    then adds the foreign keys and, finding the table, keeps its rows instead
    of recomputing the field. Both tables use ``column1`` and ``column2``.
    Returns the number of pairs inserted; a second run inserts none.
    """
    if not openupgrade.table_exists(cr, target):
        openupgrade.logged_query(
            cr,
            sql.SQL(
                """
                CREATE TABLE {target} (
                    {column1} INTEGER NOT NULL,
                    {column2} INTEGER NOT NULL,
                    PRIMARY KEY ({column1}, {column2})
                );
                COMMENT ON TABLE {target} IS {comment};
                CREATE INDEX ON {target} ({column2}, {column1})
                """
            ).format(
                target=sql.Identifier(target),
                column1=sql.Identifier(column1),
                column2=sql.Identifier(column2),
                comment=sql.Literal(
                    "RELATION BETWEEN %s AND %s"
                    % (column1.removesuffix("_id"), column2.removesuffix("_id"))
                ),
            ),
        )
    if not openupgrade.table_exists(cr, source):
        return 0
    return openupgrade.logged_query(
        cr,
        sql.SQL(
            """
            INSERT INTO {target} ({column1}, {column2})
            SELECT {column1}, {column2} FROM {source}
            ON CONFLICT DO NOTHING
            """
        ).format(
            target=sql.Identifier(target),
            source=sql.Identifier(source),
            column1=sql.Identifier(column1),
            column2=sql.Identifier(column2),
        ),
    )
