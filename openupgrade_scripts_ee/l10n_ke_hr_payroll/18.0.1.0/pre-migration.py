# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _copy_l10n_ke_disabled_to_disabled(env):
    """Copy l10n_ke_disabled data into the new generic disabled field.

    In 17.0: l10n_ke_hr_payroll defined l10n_ke_disabled (Boolean) on hr.employee.
    In 18.0: hr_payroll defines a generic disabled field on hr.employee, and
    l10n_ke_hr_payroll uses it instead.

    The hr_payroll module creates the disabled column during its update (before
    l10n_ke_hr_payroll runs), so we cannot rename — we copy the data instead.
    OpenUpgrade preserves the old l10n_ke_disabled column automatically.
    """
    if not openupgrade.column_exists(env.cr, "hr_employee", "l10n_ke_disabled"):
        return
    if not openupgrade.column_exists(env.cr, "hr_employee", "disabled"):
        # disabled column not yet created (hr_payroll hasn't run yet);
        # fall back to a simple rename
        openupgrade.rename_columns(
            env.cr, {"hr_employee": [("l10n_ke_disabled", "disabled")]}
        )
        return
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE hr_employee
        SET disabled = l10n_ke_disabled
        WHERE l10n_ke_disabled = true
          AND (disabled IS NULL OR disabled = false)
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _copy_l10n_ke_disabled_to_disabled(env)
