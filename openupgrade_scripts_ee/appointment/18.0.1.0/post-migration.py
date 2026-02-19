# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _delete_obsolete_records(env):
    openupgrade.delete_records_safely_by_xml_id(
        env,
        [
            "appointment.appointment_onboarding_create_appointment_type_step",
            "appointment.appointment_onboarding_preview_invite_step",
            "appointment.appointment_onboarding_configure_calendar_provider_step",
            "appointment.onboarding_onboarding_appointment",
        ],
    )


@openupgrade.migrate()
def migrate(env, version):
    _delete_obsolete_records(env)
