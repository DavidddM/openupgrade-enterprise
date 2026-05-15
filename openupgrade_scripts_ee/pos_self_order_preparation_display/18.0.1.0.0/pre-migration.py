# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_field_renames = [
    (
        "pos_preparation_display.order",
        "pos_preparation_display_order",
        "pos_take_away",
        "pos_takeaway",
    ),
]


@openupgrade.migrate()
def migrate(env, version):
    """Keep the take-away flag of the preparation orders under its 18.0 name.

    18.0 renamed ``pos_take_away`` to ``pos_takeaway`` with the same label and
    default; without the rename every self-order shown on a preparation
    display would lose its take-away marker.
    """
    openupgrade.rename_fields(env, _field_renames)
