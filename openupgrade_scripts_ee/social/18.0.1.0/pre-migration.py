# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _add_is_split_per_media(env):
    """Add ``is_split_per_media`` boolean column to social_post_template and
    social_post.

    In v18, social posts can have different content per media platform (split
    posting). This column is required before the per-media message fields are
    populated by child module scripts (social_facebook, social_instagram, etc.).
    """
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE social_post_template
        ADD COLUMN IF NOT EXISTS is_split_per_media boolean DEFAULT false
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE social_post
        ADD COLUMN IF NOT EXISTS is_split_per_media boolean DEFAULT false
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _add_is_split_per_media(env)
