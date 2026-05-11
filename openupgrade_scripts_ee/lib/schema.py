# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Schema helpers for many2one fields whose comodel changes in 18.0."""

from openupgradelib import openupgrade
from psycopg2 import sql


def drop_foreign_keys(cr, table, column):
    """Drop the foreign keys of ``table.column`` and nothing else.

    ``openupgrade.lift_constraints`` also matches foreign keys of other tables
    that point at ``table`` through a column with the same attribute number,
    so it is not used here.
    """
    cr.execute(
        """
        SELECT c.conname
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
        WHERE c.contype = 'f' AND t.relname = %s AND a.attname = %s
        """,
        (table, column),
    )
    for (name,) in cr.fetchall():
        openupgrade.logged_query(
            cr,
            sql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(
                sql.Identifier(table), sql.Identifier(name)
            ),
        )


def detach_column(cr, table, column):
    """Keep the 17.0 ids of a many2one in its legacy column, without foreign key.

    Run in the pre-migration of the module that switches the comodel: the
    module load then creates an empty column and its new foreign key, instead
    of re-adding the foreign key against ids the new table does not have,
    which aborts the upgrade. Returns the legacy column name; a second run
    changes nothing.
    """
    legacy = openupgrade.get_legacy_name(column)
    if openupgrade.column_exists(cr, table, column) and not (
        openupgrade.column_exists(cr, table, legacy)
    ):
        drop_foreign_keys(cr, table, column)
        openupgrade.rename_columns(cr, {table: [(column, legacy)]})
    return legacy
