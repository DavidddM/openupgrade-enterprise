# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _migrate_project_id_from_company_dependent(env):
    """Migrate project_id on planning.slot.template from company_dependent
    (ir_property) to a regular Many2one column.

    17.0: project_id (Many2one, company_dependent=True → stored in ir_property)
    18.0: project_id (regular Many2one, stored in column)

    Reads values from ir_property and populates the new column. Since
    company_dependent fields can have per-company values, we take the first
    non-null value found (templates are typically single-company anyway).

    Populates from ir_property by extracting the integer ID from res_id
    (format: 'planning.slot.template,<id>') and the integer value from
    value_reference (format: 'project.project,<id>').
    """
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE planning_slot_template
        ADD COLUMN IF NOT EXISTS project_id integer
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE planning_slot_template pst
        SET project_id = prop.project_id_int
        FROM (
            SELECT DISTINCT ON (template_id)
                CAST(SPLIT_PART(ip.res_id, ',', 2) AS integer) AS template_id,
                CAST(SPLIT_PART(ip.value_reference, ',', 2) AS integer) AS project_id_int
            FROM ir_property ip
            JOIN ir_model_fields imf ON imf.id = ip.fields_id
            WHERE imf.model = 'planning.slot.template'
              AND imf.name = 'project_id'
              AND ip.value_reference IS NOT NULL
              AND ip.value_reference != ''
              AND ip.res_id IS NOT NULL
              AND ip.res_id != ''
            ORDER BY template_id, ip.company_id NULLS LAST
        ) prop
        WHERE pst.id = prop.template_id
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _migrate_project_id_from_company_dependent(env)
