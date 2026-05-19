# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade
from psycopg2 import sql

from odoo.upgrade.lib import relation

_field_renames = [
    ("res.company", "res_company", "account_folder", "account_folder_id"),
    ("res.company", "res_company", "product_folder", "product_folder_id"),
    ("res.company", "res_company", "product_tags", "product_tag_ids"),
    (
        "res.company",
        "res_company",
        "documents_spreadsheet_folder_id",
        "document_spreadsheet_folder_id",
    ),
]

_xmlid_renames = [
    (
        "documents.documents_internal_folder",
        "documents.document_internal_folder",
    ),
    (
        "documents.documents_finance_folder",
        "documents.document_finance_folder",
    ),
    (
        "documents.documents_marketing_folder",
        "documents.document_marketing_folder",
    ),
    (
        "documents_approvals.documents_approvals_folder",
        "documents_approvals.document_approvals_folder",
    ),
    (
        "documents_fleet.documents_fleet_folder",
        "documents_fleet.document_fleet_folder",
    ),
    (
        "documents_hr.documents_hr_folder",
        "documents_hr.document_hr_folder",
    ),
    (
        "documents_hr_recruitment.documents_recruitment_folder",
        "documents_hr_recruitment.document_recruitment_folder",
    ),
    (
        "documents_product.documents_product_folder",
        "documents_product.document_product_folder",
    ),
    (
        "documents_spreadsheet.documents_spreadsheet_folder",
        "documents_spreadsheet.document_spreadsheet_folder",
    ),
    (
        "documents_project.documents_project_folder",
        "documents_project.document_project_folder",
    ),
]


def _add_document_columns(env):
    """Add new required columns to documents_document for 18.0.

    - document_token: unique access token (required, unique)
    - access_via_link / access_internal: access control selections (required)
    - company_id: was related (not stored) in 17.0, now store=True in 18.0
    """
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE documents_document
        ADD COLUMN IF NOT EXISTS document_token varchar,
        ADD COLUMN IF NOT EXISTS access_via_link varchar,
        ADD COLUMN IF NOT EXISTS access_internal varchar,
        ADD COLUMN IF NOT EXISTS company_id integer
        """,
    )


def _fill_document_defaults(env):
    """Populate required field values for existing document rows.

    - Generate unique document_token for each existing record.
    - Set access control defaults (access_via_link, access_internal); the
      internal access is then derived from the 17.0 workspace groups.
    - Ensure owner_id is set (required in 18.0, was optional in 17.0).
    - Populate company_id from the folder's company.
    - Map removed selection value 'empty' to 'binary'.
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE documents_document
        SET document_token = md5(random()::text || id::text
                                 || clock_timestamp()::text)
        WHERE document_token IS NULL
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE documents_document
        SET access_via_link = COALESCE(access_via_link, 'none'),
            access_internal = COALESCE(access_internal, 'none')
        WHERE access_via_link IS NULL OR access_internal IS NULL
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE documents_document
        SET owner_id = COALESCE(create_uid, 1)
        WHERE owner_id IS NULL
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE documents_document dd
        SET company_id = df.company_id
        FROM documents_folder df
        WHERE dd.folder_id = df.id
        AND dd.company_id IS NULL
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE documents_document
        SET type = 'binary'
        WHERE type = 'empty'
        """,
    )


def _deduplicate_tag_names(env):
    """Ensure documents_tag names are globally unique.

    In 17.0 uniqueness was per-facet: UNIQUE(facet_id, name).
    In 18.0 facets are removed and uniqueness is global: UNIQUE(name).
    Resolve duplicates by appending a numeric suffix to each translation.
    """
    openupgrade.logged_query(
        env.cr,
        """
        WITH ranked AS (
            SELECT id, name,
                   ROW_NUMBER() OVER (PARTITION BY name ORDER BY id) AS rn
            FROM documents_tag
        )
        UPDATE documents_tag dt
        SET name = (
            SELECT jsonb_object_agg(key, value || ' (' || ranked.rn::text || ')')
            FROM jsonb_each_text(dt.name) AS j(key, value)
        )
        FROM ranked
        WHERE dt.id = ranked.id
        AND ranked.rn > 1
        """,
    )


def _relax_tag_constraints(env):
    """Drop NOT NULL on documents_tag.facet_id (field removed in 18.0).

    Without this, any INSERT into documents_tag during module update
    would fail because the ORM no longer sets facet_id.
    """
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE documents_tag
        ALTER COLUMN facet_id DROP NOT NULL
        """,
    )


def _relax_document_folder_constraint(env):
    """Drop NOT NULL on documents_document.folder_id.

    In 17.0, folder_id was required (referencing documents.folder).
    In 18.0, folder_id is optional (referencing documents.document).
    Root folder-type documents have folder_id=NULL, so the NOT NULL
    constraint must be removed before inserting them.
    """
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE documents_document
        ALTER COLUMN folder_id DROP NOT NULL
        """,
    )


def _drop_folder_fk_constraints(env):
    """Drop all FK constraints referencing the documents_folder table.

    All folder_id columns across many tables will be remapped from
    documents_folder IDs to documents_document IDs. The FK constraints
    referencing the old table must be removed first.
    """
    openupgrade.logged_query(
        env.cr,
        """
        DO $$ DECLARE r RECORD;
        BEGIN
            FOR r IN (
                SELECT conname, conrelid::regclass AS tablename
                FROM pg_constraint
                WHERE confrelid = 'documents_folder'::regclass
                AND contype = 'f'
            ) LOOP
                EXECUTE 'ALTER TABLE ' || r.tablename
                    || ' DROP CONSTRAINT ' || quote_ident(r.conname);
            END LOOP;
        END $$
        """,
    )


def _insert_folders_as_documents(env):
    """Create a documents_document record for each documents_folder.

    In 18.0, documents.folder was merged into documents.document
    (type='folder'). A mapping column (_ou_from_folder_id) tracks
    which new document corresponds to which old folder.

    Note: documents_folder.name is JSONB (translate=True) but
    documents_document.name is plain varchar in 18.0, so the first
    available translation is extracted.

    A 17.0 workspace belongs to nobody; the folder is owned by OdooBot, as
    18.0 company folders are: a folder owned by a user would give that user
    edit rights and sit in the user's own drive instead of the company root.
    """
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE documents_document
        ADD COLUMN IF NOT EXISTS _ou_from_folder_id integer
        """,
    )
    owner = env.ref("base.user_root").id
    openupgrade.logged_query(
        env.cr,
        """
        INSERT INTO documents_document (
            name, active, type, company_id, owner_id,
            document_token, access_via_link, access_internal,
            create_uid, create_date, write_uid, write_date,
            _ou_from_folder_id
        )
        SELECT
            COALESCE(
                df.name ->> 'en_US',
                (SELECT v FROM jsonb_each_text(df.name) AS j(k, v) LIMIT 1),
                'Unnamed Folder'
            ),
            df.active,
            'folder',
            df.company_id,
            %(owner)s,
            md5(random()::text || df.id::text || clock_timestamp()::text),
            'none',
            'none',
            COALESCE(df.create_uid, 1),
            COALESCE(df.create_date, now() AT TIME ZONE 'UTC'),
            COALESCE(df.write_uid, 1),
            COALESCE(df.write_date, now() AT TIME ZONE 'UTC'),
            df.id
        FROM documents_folder df
        """,
        {"owner": owner},
    )
    openupgrade.logged_query(
        env.cr,
        """
        CREATE INDEX IF NOT EXISTS idx_dd_ou_from_folder_id
        ON documents_document (_ou_from_folder_id)
        WHERE _ou_from_folder_id IS NOT NULL
        """,
    )


def _remap_folder_hierarchy(env):
    """Set folder_id on new folder-type documents from parent_folder_id."""
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE documents_document dd
        SET folder_id = parent_doc.id
        FROM documents_folder df
        JOIN documents_document parent_doc
            ON parent_doc._ou_from_folder_id = df.parent_folder_id
        WHERE dd._ou_from_folder_id = df.id
        AND df.parent_folder_id IS NOT NULL
        """,
    )


def _remap_document_folder_ids(env):
    """Remap folder_id on original documents from folder IDs to document IDs."""
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE documents_document dd
        SET folder_id = new_folder.id
        FROM documents_document new_folder
        WHERE new_folder._ou_from_folder_id = dd.folder_id
        AND dd._ou_from_folder_id IS NULL
        AND dd.folder_id IS NOT NULL
        """,
    )


def _internal_access_from_groups(env):
    """Give folders and documents the internal access of their 17.0 workspace.

    17.0 opens a workspace without write and read groups to every internal
    user (read, create, edit) and restricts any other workspace to its groups
    (record rules on ``group_ids`` and ``read_group_ids``). The folder made
    from the workspace and every document in it get ``access_internal`` 'edit'
    in the first case and 'none' in the second; the post-migration lists the
    group members on the restricted ones. 17.0 ``group_ids`` has no relation
    name, so its rows are in the default table
    ``documents_folder_res_groups_rel``; ``read_group_ids`` names its table.
    """
    openupgrade.logged_query(
        env.cr,
        sql.SQL(
            """
            WITH workspace AS (
                SELECT folder.id,
                    EXISTS (
                        SELECT 1 FROM {write_groups} w
                        WHERE w.documents_folder_id = folder.id
                    ) OR EXISTS (
                        SELECT 1 FROM documents_folder_read_groups r
                        WHERE r.documents_folder_id = folder.id
                    ) AS restricted
                FROM documents_folder folder
            ), target AS (
                SELECT fd.id, workspace.restricted
                FROM documents_document fd
                JOIN workspace ON workspace.id = fd._ou_from_folder_id
                UNION ALL
                SELECT doc.id, workspace.restricted
                FROM documents_document doc
                JOIN documents_document fd ON fd.id = doc.folder_id
                JOIN workspace ON workspace.id = fd._ou_from_folder_id
                WHERE doc._ou_from_folder_id IS NULL
            )
            UPDATE documents_document doc
            SET access_internal = CASE
                WHEN target.restricted THEN 'none' ELSE 'edit'
            END
            FROM target
            WHERE doc.id = target.id
            """
        ).format(
            write_groups=sql.Identifier(
                relation.default_name("documents_folder", "res_groups")
            )
        ),
    )


def _remap_child_module_fks(env):
    """Remap FK columns in child modules from folder IDs to document IDs.

    Each column is guarded by column_exists so that modules not installed
    are silently skipped. The last three columns are listed under the names
    openupgrade.rename_fields gave them earlier, the others under their 17.0
    names.
    """
    fk_remaps = [
        ("res_company", "approvals_folder_id"),
        ("res_company", "documents_fleet_folder"),
        ("res_company", "documents_hr_folder"),
        ("res_company", "documents_payroll_folder_id"),
        ("res_company", "recruitment_folder_id"),
        ("project_project", "documents_folder_id"),
        ("sign_template", "folder_id"),
        ("documents_account_folder_setting", "folder_id"),
        ("mail_activity_type", "folder_id"),
        ("res_company", "account_folder_id"),
        ("res_company", "product_folder_id"),
        ("res_company", "document_spreadsheet_folder_id"),
    ]
    for table, column in fk_remaps:
        if openupgrade.column_exists(env.cr, table, column):
            openupgrade.logged_query(
                env.cr,
                f"""
                UPDATE {table} t
                SET {column} = dd.id
                FROM documents_document dd
                WHERE dd._ou_from_folder_id = t.{column}
                AND t.{column} IS NOT NULL
                """,
            )


def _update_folder_xmlids(env):
    """Update ir_model_data for documents.folder to documents.document.

    Points each XML ID to the new documents_document record that was
    created from the corresponding documents_folder record.
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE ir_model_data imd
        SET model = 'documents.document',
            res_id = dd.id
        FROM documents_document dd
        WHERE imd.model = 'documents.folder'
        AND dd._ou_from_folder_id = imd.res_id
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _add_document_columns(env)
    _fill_document_defaults(env)
    openupgrade.rename_fields(env, _field_renames)
    _deduplicate_tag_names(env)
    _relax_tag_constraints(env)
    _relax_document_folder_constraint(env)
    _drop_folder_fk_constraints(env)
    _insert_folders_as_documents(env)
    _remap_folder_hierarchy(env)
    _remap_document_folder_ids(env)
    _internal_access_from_groups(env)
    _remap_child_module_fks(env)
    _update_folder_xmlids(env)
    openupgrade.rename_xmlids(env.cr, _xmlid_renames)
