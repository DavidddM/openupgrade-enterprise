# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


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


@openupgrade.migrate()
def migrate(env, version):
    _cleanup_stale_model_data(env)
    _drop_facet_fk_constraint(env)
