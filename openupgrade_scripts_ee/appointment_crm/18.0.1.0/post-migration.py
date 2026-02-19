# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _delete_obsolete_records(env):
    openupgrade.delete_records_safely_by_xml_id(
        env,
        [
            "appointment_crm.appointment_crm_tag",
        ],
    )


@openupgrade.migrate()
def migrate(env, version):
    _delete_obsolete_records(env)
