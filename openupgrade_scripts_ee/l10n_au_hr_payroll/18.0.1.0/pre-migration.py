# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_column_renames = {
    "hr_contract": [
        ("l10n_au_withholding_variation", None),
        ("l10n_au_withholding_variation_amount", None),
        ("l10n_au_employment_basis_code", None),
        ("l10n_au_country_code", None),
    ],
    "hr_payroll_structure_type": [
        ("l10n_au_tax_treatment_category", None),
    ],
}

# These columns may not exist if they were non-stored computes in v17
_optional_column_renames = {
    "hr_contract": [
        ("l10n_au_tax_treatment_option", None),
    ],
}

_field_renames = [
    (
        "hr.employee",
        "hr_employee",
        "l10n_au_previous_id_bms",
        "l10n_au_previous_payroll_id",
    ),
]


def _rename_optional_columns(env):
    """Rename columns that may not exist (non-stored computed in v17)."""
    for table, columns in _optional_column_renames.items():
        for old_name, new_name in columns:
            if openupgrade.column_exists(env.cr, table, old_name):
                openupgrade.rename_columns(env.cr, {table: [(old_name, new_name)]})


def _scale_casual_loading(env):
    """Scale l10n_au_casual_loading from 0-100 to 0-1 range on hr_contract."""
    if openupgrade.column_exists(env.cr, "hr_contract", "l10n_au_casual_loading"):
        openupgrade.logged_query(
            env.cr,
            """
            UPDATE hr_contract
            SET l10n_au_casual_loading = l10n_au_casual_loading / 100.0
            WHERE l10n_au_casual_loading > 1
            """,
        )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_columns(env.cr, _column_renames)
    _rename_optional_columns(env)
    openupgrade.rename_fields(env, _field_renames)
    _scale_casual_loading(env)
