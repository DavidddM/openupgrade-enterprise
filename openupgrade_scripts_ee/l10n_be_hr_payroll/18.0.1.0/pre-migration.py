# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_column_renames = {
    "hr_contract": [
        ("fiscal_voluntary_rate", None),
        ("fiscal_voluntarism", None),
    ],
    "res_company": [
        ("onss_pem_passphrase", None),
    ],
}


@openupgrade.migrate()
def migrate(env, version):
    """Keep the 17.0 columns that 18.0 drops or moves under legacy names.

    ``onss_pem_passphrase`` is the only ONSS company field with a column (the
    certificate and key are attachments); the post-migration reads it as the
    password of the migrated ONSS key.
    """
    openupgrade.rename_columns(env.cr, _column_renames)
