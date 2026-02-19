# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _migrate_company_ids_to_company_id(env):
    """Migrate M2M company_ids to M2O company_id on worksheet.template."""
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE worksheet_template
        ADD COLUMN IF NOT EXISTS company_id integer
        """,
    )
    if openupgrade.table_exists(env.cr, "worksheet_template_res_company_rel"):
        openupgrade.logged_query(
            env.cr,
            """
            UPDATE worksheet_template wt
            SET company_id = rel.res_company_id
            FROM (
                SELECT DISTINCT ON (worksheet_template_id)
                    worksheet_template_id, res_company_id
                FROM worksheet_template_res_company_rel
                ORDER BY worksheet_template_id, res_company_id
            ) rel
            WHERE wt.id = rel.worksheet_template_id
            AND wt.company_id IS NULL
            """,
        )


@openupgrade.migrate()
def migrate(env, version):
    _migrate_company_ids_to_company_id(env)
