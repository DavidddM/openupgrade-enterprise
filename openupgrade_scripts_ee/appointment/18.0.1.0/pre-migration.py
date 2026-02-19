# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_field_renames = [
    (
        "appointment.type",
        "appointment_type",
        "resource_manual_confirmation",
        "appointment_manual_confirmation",
    ),
]


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_fields(env, _field_renames)
