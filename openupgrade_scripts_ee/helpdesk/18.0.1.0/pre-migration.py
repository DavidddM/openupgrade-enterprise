# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Rename helpdesk xmlids where "7dayssuccess" was corrected to "7days_success".

In 17.0, the act_window_view records for the 7days_success action (id=557)
used xmlids with "7dayssuccess" (no underscore). In 18.0, these were corrected
to "7days_success" (with underscore) in helpdesk_ticket_views.xml. The
"7dayssuccess" naming is still used in helpdesk_ticket_analysis_views.xml for
the separate 7dayssuccess action (id=560), so only the records referencing the
7days_success action (tree, kanban, activity) are renamed.
"""

from openupgradelib import openupgrade

_xmlid_renames = [
    (
        "helpdesk.helpdesk_ticket_action_7dayssuccess_tree",
        "helpdesk.helpdesk_ticket_action_7days_success_tree",
    ),
    (
        "helpdesk.helpdesk_ticket_action_7dayssuccess_kanban",
        "helpdesk.helpdesk_ticket_action_7days_success_kanban",
    ),
    (
        "helpdesk.helpdesk_ticket_action_7dayssuccess_activity",
        "helpdesk.helpdesk_ticket_action_7days_success_activity",
    ),
]


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_xmlids(env.cr, _xmlid_renames)
