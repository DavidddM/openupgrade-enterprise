# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

from odoo.upgrade.lib import relation

_field_renames = [
    (
        "studio.approval.rule",
        "studio_approval_rule",
        "group_id",
        "approval_group_id",
    ),
]


def _copy_users_to_notify(env):
    """Carry the users to notify of every approval rule to the 18.0 relation.

    17.0 declares ``users_to_notify`` without ``relation=``, so its pairs are
    in ``res_users_studio_approval_rule_rel``; 18.0 names the relation
    ``approval_rule_users_to_notify_rel`` with the same two columns. Created
    before the load, the table keeps the pairs instead of starting empty.
    """
    relation.copy_pairs(
        env.cr,
        relation.default_name("studio_approval_rule", "res_users"),
        "approval_rule_users_to_notify_rel",
        "studio_approval_rule_id",
        "res_users_id",
    )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_fields(env, _field_renames)
    _copy_users_to_notify(env)
