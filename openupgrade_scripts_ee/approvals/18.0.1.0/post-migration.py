# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _delete_obsolete_records(env):
    openupgrade.delete_records_safely_by_xml_id(
        env,
        [
            "approvals.approval_request_request_owner_rule",
            "approvals.approval_request_write_request_owner_rule",
            "approvals.approval_request_approvers_rule",
        ],
    )


@openupgrade.migrate()
def migrate(env, version):
    _delete_obsolete_records(env)
