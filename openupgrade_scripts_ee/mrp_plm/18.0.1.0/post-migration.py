# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _migrate_mrp_plm_documents(env):
    """Copy origin_attachment_id from mrp_document to product_document.

    The community mrp post-migration creates product_document records from
    mrp_document and stores the old ID in a legacy link column. The ECOs'
    displayed image is remapped through the same link in pre-migration,
    before the module load adds its foreign key to product_document.
    """
    link_column = openupgrade.get_legacy_name("mrp_document_id")
    if not openupgrade.column_exists(env.cr, "product_document", link_column):
        return
    if openupgrade.column_exists(env.cr, "mrp_document", "origin_attachment_id"):
        openupgrade.logged_query(
            env.cr,
            f"""
            UPDATE product_document pd
            SET origin_attachment_id = md.origin_attachment_id
            FROM mrp_document md
            WHERE pd.{link_column} = md.id
            AND md.origin_attachment_id IS NOT NULL
            """,
        )


@openupgrade.migrate()
def migrate(env, version):
    _migrate_mrp_plm_documents(env)
