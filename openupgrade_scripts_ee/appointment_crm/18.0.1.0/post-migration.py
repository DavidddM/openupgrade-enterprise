# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _keep_appointment_tag(env):
    """Keep the Appointment tag on the leads 17.0 gave it to.

    17.0 tags every lead an appointment creates with ``appointment_crm_tag``;
    18.0 no longer ships the tag. Deleting the record would take it off those
    leads, so only its xmlid goes and the tag stays as a tag of the database.
    """
    openupgrade.logged_query(
        env.cr,
        """
        DELETE FROM ir_model_data
        WHERE module = 'appointment_crm' AND name = 'appointment_crm_tag'
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _keep_appointment_tag(env)
