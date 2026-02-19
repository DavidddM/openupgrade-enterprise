# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_field_renames = [
    (
        "discuss.channel",
        "discuss_channel",
        "whatsapp_mail_message_id",
        "last_wa_mail_message_id",
    ),
]


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_fields(env, _field_renames)
