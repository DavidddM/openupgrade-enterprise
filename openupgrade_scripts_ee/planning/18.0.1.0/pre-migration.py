# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _convert_planning_allow_self_unassign_to_selection(env):
    """Convert Boolean planning_allow_self_unassign to Selection
    planning_employee_unavailabilities on res.company.

    17.0: planning_allow_self_unassign (Boolean, default=False)
    18.0: planning_employee_unavailabilities (Selection: 'switch'|'unassign',
          default='switch', required)

    Mapping: True → 'unassign', False → 'switch'
    """
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE res_company
        ADD COLUMN IF NOT EXISTS planning_employee_unavailabilities varchar
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE res_company
        SET planning_employee_unavailabilities = CASE
            WHEN planning_allow_self_unassign = true THEN 'unassign'
            ELSE 'switch'
        END
        """,
    )


def _convert_duration_to_duration_days(env):
    """Convert Float duration (hours) to Integer duration_days on
    planning.slot.template.

    17.0: duration (Float, hours, stored) + duration_days (computed, NOT stored)
    18.0: duration removed, duration_days (Integer, stored, default=1)

    Logic: duration_days = CEIL(duration / 8.0), minimum 1.
    Records where duration was NULL get default value of 1.
    """
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE planning_slot_template
        ADD COLUMN IF NOT EXISTS duration_days integer
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE planning_slot_template
        SET duration_days = GREATEST(1, CEIL(duration / 8.0))
        WHERE duration IS NOT NULL
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE planning_slot_template
        SET duration_days = 1
        WHERE duration_days IS NULL
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _convert_planning_allow_self_unassign_to_selection(env)
    _convert_duration_to_duration_days(env)
