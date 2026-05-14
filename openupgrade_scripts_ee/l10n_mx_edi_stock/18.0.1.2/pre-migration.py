# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_PACKAGE_TYPE = "l10n_mx_edi_hazard_package_type"


@openupgrade.migrate()
def migrate(env, version):
    """Keep the 17.0 packaging type of hazardous products away from the load.

    18.0 computes ``l10n_mx_edi_hazard_package_type`` together with the new
    ``l10n_mx_edi_hazardous_material_code_id`` from the UNSPSC code and empties
    both for every product whose code is not flagged hazardous when the load
    computes the new column. The 17.0 value is copied to a legacy column here;
    the post-migration puts it back. A second run keeps the first copy.
    """
    legacy = openupgrade.get_legacy_name(_PACKAGE_TYPE)
    if openupgrade.column_exists(
        env.cr, "product_template", _PACKAGE_TYPE
    ) and not openupgrade.column_exists(env.cr, "product_template", legacy):
        openupgrade.copy_columns(
            env.cr, {"product_template": [(_PACKAGE_TYPE, legacy, None)]}
        )
