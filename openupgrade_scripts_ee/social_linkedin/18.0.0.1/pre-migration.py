# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _prefill_linkedin_message(env):
    """Copy the shared ``message`` field to the new ``linkedin_message``
    per-media field on social_post_template and social_post.
    """
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE social_post_template
        ADD COLUMN IF NOT EXISTS linkedin_message text
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE social_post_template
        SET linkedin_message = message
        WHERE message IS NOT NULL
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE social_post
        ADD COLUMN IF NOT EXISTS linkedin_message text
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE social_post
        SET linkedin_message = message
        WHERE message IS NOT NULL
        """,
    )


def _prefill_linkedin_image_ids(env):
    """Create the new LinkedIn-specific image M2M relation tables and copy
    existing shared image attachments into them.
    """
    openupgrade.logged_query(
        env.cr,
        """
        CREATE TABLE IF NOT EXISTS template_linkedin_image_ids_rel (
            social_post_template_id integer NOT NULL,
            ir_attachment_id integer NOT NULL,
            PRIMARY KEY (social_post_template_id, ir_attachment_id)
        )
        """,
    )
    if openupgrade.table_exists(env.cr, "social_post_template_ir_attachment_rel"):
        openupgrade.logged_query(
            env.cr,
            """
            INSERT INTO template_linkedin_image_ids_rel
                (social_post_template_id, ir_attachment_id)
            SELECT social_post_template_id, ir_attachment_id
            FROM social_post_template_ir_attachment_rel
            ON CONFLICT DO NOTHING
            """,
        )
    openupgrade.logged_query(
        env.cr,
        """
        CREATE TABLE IF NOT EXISTS linkedin_image_ids_rel (
            social_post_id integer NOT NULL,
            ir_attachment_id integer NOT NULL,
            PRIMARY KEY (social_post_id, ir_attachment_id)
        )
        """,
    )
    if openupgrade.table_exists(env.cr, "social_post_ir_attachment_rel"):
        openupgrade.logged_query(
            env.cr,
            """
            INSERT INTO linkedin_image_ids_rel
                (social_post_id, ir_attachment_id)
            SELECT social_post_id, ir_attachment_id
            FROM social_post_ir_attachment_rel
            ON CONFLICT DO NOTHING
            """,
        )


@openupgrade.migrate()
def migrate(env, version):
    _prefill_linkedin_message(env)
    _prefill_linkedin_image_ids(env)
