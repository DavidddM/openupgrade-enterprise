# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

from odoo.upgrade.lib import schema


@openupgrade.migrate()
def migrate(env, version):
    """Move the 17.0 certificate ids of the invoices out of the module load.

    account.move.l10n_mx_edi_certificate_id points at l10n_mx_edi.certificate
    in 17.0 and at certificate.certificate in 18.0; the post-migration fills
    the new column from the legacy one once the certificates exist.
    """
    schema.detach_column(env.cr, "account_move", "l10n_mx_edi_certificate_id")
