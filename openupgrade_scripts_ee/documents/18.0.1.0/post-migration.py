# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade
from psycopg2 import sql

from odoo import Command
from odoo.upgrade.lib import data, relation

_logger = logging.getLogger(__name__)


def _cleanup_stale_model_data(env):
    """Delete ir_model_data entries for models removed in 18.0.

    These models were replaced or merged into documents.document:
    - documents.workflow.rule / .action → replaced by ir.actions.server
    - documents.facet → removed (tags flattened)
    - documents.share → replaced by documents.access
    """
    openupgrade.logged_query(
        env.cr,
        """
        DELETE FROM ir_model_data
        WHERE model IN (
            'documents.workflow.rule',
            'documents.workflow.action',
            'documents.facet',
            'documents.share'
        )
        """,
    )


def _drop_facet_fk_constraint(env):
    """Drop FK constraint on documents_tag.facet_id referencing documents_facet.

    The facet_id column stays in the table (Odoo does not drop stale columns)
    but the FK constraint would interfere with any future table operations.
    """
    openupgrade.logged_query(
        env.cr,
        """
        DO $$ DECLARE r RECORD;
        BEGIN
            FOR r IN (
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'documents_tag'::regclass
                AND confrelid = 'documents_facet'::regclass
                AND contype = 'f'
            ) LOOP
                EXECUTE 'ALTER TABLE documents_tag DROP CONSTRAINT '
                    || quote_ident(r.conname);
            END LOOP;
        END $$
        """,
    )


def _administrators_keep_full_access(env):
    """Make the 17.0 documents administrators 18.0 system administrators.

    17.0 lets its documents administrators read and edit every workspace and
    document (manager record rules ``[(1, '=', 1)]``). In 18.0 an
    administrator edits only what internal users may access, and only the
    new system administrator group sees everything (``user_permission``), so
    without it the administrators lose the restricted workspaces. The default
    user template keeps the 18.0 default for new users.
    """
    manager = env.ref("documents.group_documents_manager")
    system = env.ref("documents.group_documents_system")
    template = env.ref("base.default_user", raise_if_not_found=False)
    users = (
        manager.with_context(active_test=False).users.filtered(
            lambda user: not user.share and user != template
        )
        - system.with_context(active_test=False).users
    )
    if users:
        system.write({"users": [Command.link(user.id) for user in users]})
    _logger.info("%s documents administrators get full access", len(users))


def _access_from_groups(env):
    """List the 17.0 workspace group members on restricted folders and documents.

    A member of a write group gets the role 'edit', a member of a read group
    'view' (the higher role wins), on the folder made from the workspace and
    on its documents, except where "own documents only" limited that group to
    the member's own documents (owners edit their documents in 18.0 anyway).
    Only internal users are listed, as the 17.0 rules applied to them only;
    system administrators and the document owner need no row. A second run
    adds nothing.
    """
    system = env.ref("documents.group_documents_system")
    openupgrade.logged_query(
        env.cr,
        sql.SQL(
            """
            WITH member AS (
                SELECT w.documents_folder_id AS workspace_id, g.uid, 'edit' AS role
                FROM {write_groups} w
                JOIN res_groups_users_rel g ON g.gid = w.res_groups_id
                UNION ALL
                SELECT r.documents_folder_id, g.uid, 'view'
                FROM documents_folder_read_groups r
                JOIN res_groups_users_rel g ON g.gid = r.res_groups_id
            ), target AS (
                SELECT fd.id AS document_id, fd.owner_id, member.uid, member.role
                FROM documents_document fd
                JOIN member ON member.workspace_id = fd._ou_from_folder_id
                UNION ALL
                SELECT doc.id, doc.owner_id, member.uid, member.role
                FROM documents_document doc
                JOIN documents_document fd ON fd.id = doc.folder_id
                JOIN documents_folder workspace ON workspace.id = fd._ou_from_folder_id
                JOIN member ON member.workspace_id = workspace.id
                WHERE doc._ou_from_folder_id IS NULL
                    AND CASE member.role
                        WHEN 'edit'
                            THEN NOT coalesce(workspace.user_specific_write, false)
                        ELSE NOT coalesce(workspace.user_specific, false)
                    END
            )
            INSERT INTO documents_access (document_id, partner_id, role)
            SELECT target.document_id, users.partner_id,
                CASE WHEN bool_or(target.role = 'edit') THEN 'edit' ELSE 'view' END
            FROM target
            JOIN res_users users ON users.id = target.uid
            WHERE NOT users.share
                AND users.id IS DISTINCT FROM target.owner_id
                AND NOT EXISTS (
                    SELECT 1 FROM res_groups_users_rel s
                    WHERE s.gid = %(system)s AND s.uid = users.id
                )
            GROUP BY target.document_id, users.partner_id
            ON CONFLICT DO NOTHING
            """
        ).format(
            write_groups=sql.Identifier(
                relation.default_name("documents_folder", "res_groups")
            )
        ),
        {"system": system.id},
    )


def _server_actions(env):
    """Create the 18.0 document server actions that an update skips.

    They are ``forcecreate="0"`` records of a ``noupdate`` block, so the update
    from 17.0, which had none of them, does not create them; documents_sign,
    which 18.0 installs during the same update when sign comes in (the 18.0
    l10n_in_reports depends on sign), refers to the activity action and its
    load would abort. The actions that need the 18.0 tags, which a 17.0
    database does not have, are left out.
    """
    data.load_missing_records(env, "documents", "data/ir_actions_server_data.xml")


@openupgrade.migrate()
def migrate(env, version):
    _cleanup_stale_model_data(env)
    _drop_facet_fk_constraint(env)
    _administrators_keep_full_access(env)
    _access_from_groups(env)
    _server_actions(env)
