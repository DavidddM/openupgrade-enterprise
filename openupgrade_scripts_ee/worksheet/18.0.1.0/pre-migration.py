# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade
from psycopg2 import sql

from odoo.upgrade.lib import relation

_logger = logging.getLogger(__name__)


def _company_ids_to_company_id(env):
    """Turn the 17.0 company list of worksheet templates into one company.

    17.0 ``company_ids`` has no relation name, so its rows are in the default
    table ``res_company_worksheet_template_rel``. A template of exactly one
    company keeps it; a template of no company or of several stays empty,
    which 18.0 reads as available to every company (18.0 cannot restrict a
    template to several companies and refuses to restrict one that tasks of
    other companies use). Runs once: the column it adds marks it done.
    """
    cr = env.cr
    if openupgrade.column_exists(cr, "worksheet_template", "company_id"):
        return
    openupgrade.logged_query(
        cr, "ALTER TABLE worksheet_template ADD COLUMN company_id integer"
    )
    table = relation.default_name("res_company", "worksheet_template")
    if not openupgrade.table_exists(cr, table):
        return
    openupgrade.logged_query(
        cr,
        sql.SQL(
            """
            UPDATE worksheet_template template
            SET company_id = rel.company_id
            FROM (
                SELECT worksheet_template_id, min(res_company_id) AS company_id
                FROM {table}
                GROUP BY worksheet_template_id
                HAVING count(*) = 1
            ) rel
            WHERE template.id = rel.worksheet_template_id
            """
        ).format(table=sql.Identifier(table)),
    )
    cr.execute(
        sql.SQL(
            """
            SELECT count(*) FROM (
                SELECT worksheet_template_id FROM {table}
                GROUP BY worksheet_template_id HAVING count(*) > 1
            ) several
            """
        ).format(table=sql.Identifier(table))
    )
    several = cr.fetchone()[0]
    if several:
        _logger.info(
            "%s worksheet templates of several companies are now open to all",
            several,
        )


@openupgrade.migrate()
def migrate(env, version):
    _company_ids_to_company_id(env)
