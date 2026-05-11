# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade
from psycopg2 import sql

from odoo.upgrade.lib import certificate


def _migrate_cl_certificates(env):
    """Migrate l10n_cl.certificate to certificate.certificate.

    17.0 stores the PFX (PKCS#12) file in the ``signature_key_file`` attachment
    and its password in ``signature_pass_phrase``; the stored ``certificate``
    column is only the public PEM, so it is not used. The owner, the SII
    tokens and the subject serial number move to the fields l10n_cl_edi adds
    to certificate.certificate (``last_rest_token`` exists only where
    l10n_cl_edi_boletas was installed). The companies find their certificates
    through ``company_id``, so there is no link to remap.
    """
    if not openupgrade.table_exists(env.cr, "l10n_cl_certificate"):
        return
    values = ["user_id", "last_token", "token_time", "subject_serial_number"]
    if openupgrade.column_exists(env.cr, "l10n_cl_certificate", "last_rest_token"):
        values.append("last_rest_token")
    query = sql.SQL(
        """
        SELECT id, company_id, signature_filename AS name,
            signature_pass_phrase AS pkcs12_password, {}
        FROM l10n_cl_certificate
        ORDER BY id
        """
    ).format(sql.SQL(", ").join(map(sql.Identifier, values)))
    certificate.migrate(
        env, "l10n_cl.certificate", query, "signature_key_file", values=values
    )


@openupgrade.migrate()
def migrate(env, version):
    _migrate_cl_certificates(env)
