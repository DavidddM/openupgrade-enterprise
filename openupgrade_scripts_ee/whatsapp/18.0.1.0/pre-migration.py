# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _last_customer_message(env):
    """Store the last message of each conversation's WhatsApp partner.

    17.0 computes the 24-hour reply window of a WhatsApp conversation from the
    last message its WhatsApp partner wrote in it; 18.0 stores that message in
    ``last_wa_mail_message_id`` and computes the window from it. The 17.0
    ``whatsapp_mail_message_id`` is another message, the one of the record the
    conversation was opened from, which 18.0 no longer keeps. The column is
    made before the module load; a conversation that already has a value keeps
    it.
    """
    openupgrade.logged_query(
        env.cr,
        "ALTER TABLE discuss_channel"
        " ADD COLUMN IF NOT EXISTS last_wa_mail_message_id integer",
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE discuss_channel channel
        SET last_wa_mail_message_id = last.message_id
        FROM (
            SELECT message.res_id, max(message.id) AS message_id
            FROM mail_message message
            JOIN discuss_channel conversation ON conversation.id = message.res_id
            WHERE message.model = 'discuss.channel'
                AND message.author_id = conversation.whatsapp_partner_id
            GROUP BY message.res_id
        ) last
        WHERE channel.id = last.res_id
            AND channel.channel_type = 'whatsapp'
            AND channel.last_wa_mail_message_id IS NULL
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _last_customer_message(env)
