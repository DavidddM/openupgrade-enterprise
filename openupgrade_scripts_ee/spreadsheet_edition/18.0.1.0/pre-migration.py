# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _rename_revision_id_to_revision_uuid(env):
    """Rename revision_id column to revision_uuid on spreadsheet_revision.

    In 18.0 the field was renamed from revision_id to revision_uuid.
    The column type (Char) and data remain identical.
    """
    openupgrade.rename_columns(
        env.cr,
        {"spreadsheet_revision": [("revision_id", "revision_uuid")]},
    )


def _convert_parent_revision_id_char_to_m2o(env):
    """Convert parent_revision_id from Char (UUID string) to Many2one (FK).

    In 17.0: parent_revision_id is a required Char field storing the UUID
    string of the parent revision (empty string '' for root revisions).

    In 18.0: parent_revision_id is a Many2one to spreadsheet.revision
    (NULL for root revisions).

    Strategy:
    1. Preserve the old Char column as ou_legacy_parent_revision_id
    2. Create a new INTEGER column parent_revision_id
    3. Populate via self-join: match the UUID string to the record ID
    """
    if not openupgrade.column_exists(
        env.cr, "spreadsheet_revision", "parent_revision_id"
    ):
        return
    # Step 1: Rename old Char column to preserve it
    openupgrade.rename_columns(
        env.cr,
        {
            "spreadsheet_revision": [
                ("parent_revision_id", "ou_legacy_parent_revision_id")
            ]
        },
    )
    # Step 2: Create new INTEGER column for the Many2one FK
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE spreadsheet_revision
        ADD COLUMN parent_revision_id INTEGER
        """,
    )
    # Step 3: Populate the FK by matching UUID strings.
    # Parent and child must share the same (res_model, res_id) to be in the
    # same revision chain.
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE spreadsheet_revision sr
        SET parent_revision_id = parent.id
        FROM spreadsheet_revision parent
        WHERE parent.revision_uuid = sr.ou_legacy_parent_revision_id
          AND parent.res_model = sr.res_model
          AND parent.res_id = sr.res_id
          AND sr.ou_legacy_parent_revision_id IS NOT NULL
          AND sr.ou_legacy_parent_revision_id != ''
        """,
    )
    # Step 4: Drop the old unique constraint (replaced by partial indexes
    # created by the model's init() method in 18.0)
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE spreadsheet_revision
        DROP CONSTRAINT IF EXISTS spreadsheet_revision_parent_revision_unique
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _rename_revision_id_to_revision_uuid(env)
    _convert_parent_revision_id_char_to_m2o(env)
