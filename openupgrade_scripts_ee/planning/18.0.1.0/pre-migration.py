# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import datetime
import logging
import math

import pytz
from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


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


def _planned_end(calendar, tz, today, start, duration):
    """End hour and working-day span of a 17.0 shift template.

    Plans the shift as 17.0 computed ``end_time``: today at the start hour in
    the planning timezone, plus ``duration`` working hours of the company
    calendar, leaves included. The span counts the working days the shift
    touches, which is what 18.0 plans a template's ``duration_days`` over. A
    duration the calendar cannot plan, or a company without calendar (17.0
    refused to display either), falls back to clock hours.
    """
    start_dt = tz.localize(
        datetime.datetime.combine(
            today,
            datetime.time(int(start), min(59, round(math.modf(start)[0] * 60))),
        )
    )
    end_dt = calendar and calendar.plan_hours(duration, start_dt, compute_leaves=True)
    if not end_dt:
        total = start + duration
        days = max(1, math.ceil(total / 24))
        end = total % 24
        if end < start and days < 2:
            days = 2
        return end, days
    if duration == 0 and start_dt.hour == 0:
        end_dt = end_dt.replace(hour=0)
    intervals = calendar._work_intervals_batch(start_dt, end_dt)[False]
    days = len({begin.astimezone(tz).date() for begin, _end, _meta in intervals})
    return end_dt.hour + end_dt.minute / 60.0, max(1, days)


def _template_end_time_and_days(env):
    """Store the end hour and day span of every 17.0 shift template.

    17.0 computes ``end_time`` and ``duration_days`` without storing them,
    from ``start_time``, ``duration`` (hours) and the company calendar; 18.0
    stores both and drops ``duration``. The columns are made here, before the
    module load would create them and write the defaults 17.0 and 1 into every
    template. The calendar, timezone and day are those 17.0 used to display a
    template to the user running the upgrade: the user's company calendar,
    the user's timezone (UTC without one) and today. Runs once: the columns it
    adds mark it done.
    """
    cr = env.cr
    if openupgrade.column_exists(cr, "planning_slot_template", "end_time"):
        return
    openupgrade.logged_query(
        cr,
        """
        ALTER TABLE planning_slot_template
        ADD COLUMN end_time double precision,
        ADD COLUMN IF NOT EXISTS duration_days integer
        """,
    )
    calendar = env.company.resource_calendar_id
    tz = pytz.timezone(env.user.tz or "UTC")
    today = datetime.date.today()
    cr.execute(
        """
        SELECT id, coalesce(start_time, 0), coalesce(duration, 0)
        FROM planning_slot_template
        ORDER BY id
        """
    )
    templates = cr.fetchall()
    for template_id, start, duration in templates:
        end, days = _planned_end(calendar, tz, today, start, duration)
        cr.execute(
            """
            UPDATE planning_slot_template
            SET end_time = %s, duration_days = %s
            WHERE id = %s
            """,
            (end, days, template_id),
        )
    _logger.info(
        "Planned the end hour of %s shift templates on calendar %s (%s, %s)",
        len(templates),
        calendar.id,
        tz.zone,
        today,
    )


@openupgrade.migrate()
def migrate(env, version):
    _convert_planning_allow_self_unassign_to_selection(env)
    _template_end_time_and_days(env)
