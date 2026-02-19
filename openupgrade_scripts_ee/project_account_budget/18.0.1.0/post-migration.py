# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.delete_records_safely_by_xml_id(
        env,
        [
            "project_account_budget.crossovered_budget_line_0",
            "project_account_budget.crossovered_budget_line_1",
            "project_account_budget.crossovered_budget_line_2",
            "project_account_budget.crossovered_budget_line_3",
            "project_account_budget.crossovered_budget_line_4",
            "project_account_budget.crossovered_budget_line_5",
        ],
    )
