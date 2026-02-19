# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _prefill_push_notification_message(env):
    """Copy the shared ``message`` field to the new
    ``push_notification_message`` per-media field on social_post_template
    and social_post.
    """
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE social_post_template
        ADD COLUMN IF NOT EXISTS push_notification_message text
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE social_post_template
        SET push_notification_message = message
        WHERE message IS NOT NULL
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE social_post
        ADD COLUMN IF NOT EXISTS push_notification_message text
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE social_post
        SET push_notification_message = message
        WHERE message IS NOT NULL
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _prefill_push_notification_message(env)
