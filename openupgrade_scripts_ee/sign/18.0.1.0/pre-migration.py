# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade
from psycopg2 import sql

_logger = logging.getLogger(__name__)


def _refused_to_canceled(env):
    """Move refused requests and signers to the canceled state.

    18.0 merged 'refused' into 'canceled' on ``sign.request.state`` and
    ``sign.request.item.state``: refusing now writes 'canceled'. A 17.0 row
    keeps 'refused' otherwise, a value 18.0 can neither display nor filter.
    """
    for table in ("sign_request", "sign_request_item"):
        openupgrade.logged_query(
            env.cr,
            sql.SQL("UPDATE {} SET state = 'canceled' WHERE state = 'refused'").format(
                sql.Identifier(table)
            ),
        )


def _report_ignored_signers(env):
    """Report the signers who ignored a request; 18.0 has no such flag.

    In 17.0 ignoring only hid a request from the signer's list of documents to
    sign and from the reminders: the signer and the request stayed open and
    could still sign. 18.0 cancels the whole request instead. Canceling
    requests that the other signers can still complete would close documents
    17.0 kept open, so the signers stay 'sent' and are listed here.
    """
    if not openupgrade.column_exists(env.cr, "sign_request_item", "ignored"):
        return
    env.cr.execute(
        """
        SELECT count(*), string_agg(item.id::text, ', ' ORDER BY item.id)
        FROM sign_request_item item
        JOIN sign_request request ON request.id = item.sign_request_id
        WHERE item.ignored AND item.state = 'sent' AND request.state = 'sent'
        """
    )
    count, ids = env.cr.fetchone()
    if count:
        _logger.info(
            "%s signers had ignored an open request in 17.0 and stay to sign: %s",
            count,
            ids,
        )


@openupgrade.migrate()
def migrate(env, version):
    _refused_to_canceled(env)
    _report_ignored_signers(env)
