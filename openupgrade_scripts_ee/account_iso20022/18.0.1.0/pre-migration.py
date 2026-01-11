# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_field_renames = [
    ("res.company", "res_company", "sepa_orgid_id", "iso20022_orgid_id"),
    ("res.company", "res_company", "sepa_orgid_issr", "iso20022_orgid_issr"),
    (
        "res.company",
        "res_company",
        "sepa_initiating_party_name",
        "iso20022_initiating_party_name",
    ),
    ("res.company", "res_company", "account_sepa_lei", "iso20022_lei"),
    ("res.partner", "res_partner", "account_sepa_lei", "iso20022_lei"),
    (
        "account.batch.payment",
        "account_batch_payment",
        "sct_batch_booking",
        "iso20022_batch_booking",
    ),
    ("account.payment", "account_payment", "sepa_uetr", "iso20022_uetr"),
]

_xmlid_renames = [
    (
        "account_sepa.account_payment_method_sepa_ct",
        "account_iso20022.account_payment_method_sepa_ct",
    ),
]


def _handle_sct_generic_removal(env):
    if openupgrade.column_exists(env.cr, "account_batch_payment", "sct_generic"):
        openupgrade.logged_query(
            env.cr,
            """
            ALTER TABLE account_batch_payment
            DROP COLUMN IF EXISTS sct_generic
            """,
        )


def _migrate_sepa_pain_version(env):
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_journal
        SET sepa_pain_version = 'pain.001.001.03'
        WHERE sepa_pain_version = 'pain.001.001.03.se'
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_journal
        SET sepa_pain_version = 'pain.001.001.03'
        WHERE sepa_pain_version = 'pain.001.001.03.ch.02'
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_journal
        SET sepa_pain_version = 'pain.001.001.09'
        WHERE sepa_pain_version = 'iso_20022'
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_fields(env, _field_renames)
    openupgrade.rename_xmlids(env.cr, _xmlid_renames)
    _handle_sct_generic_removal(env)
    _migrate_sepa_pain_version(env)
