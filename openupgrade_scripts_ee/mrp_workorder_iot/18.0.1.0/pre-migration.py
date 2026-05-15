# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_trigger_actions = [
    ("skip", "SKIP"),
    ("pause", "PAUS"),
    ("prev", "PREV"),
    ("next", "NEXT"),
    ("validate", "VALI"),
    ("cloMO", "CLMO"),
    ("cloWO", "CLWO"),
    ("finish", "FINI"),
    ("record", "RECO"),
    ("cancel", "CANC"),
    ("print-op", "PROP"),
    ("print-slip", "PRSL"),
    ("print", "PRNT"),
    ("pack", "PACK"),
    ("scrap", "SCRA"),
]


@openupgrade.migrate()
def migrate(env, version):
    """Give the IoT trigger actions their 18.0 keys.

    18.0 renamed fifteen of the sixteen keys of ``iot.trigger.action`` and kept
    their labels; only 'picture' is unchanged. The ORM keeps the stored 17.0
    keys, which 18.0 can neither display nor run. No new key is an old one, so
    the order of the updates does not matter and a second run changes nothing.
    """
    for old, new in _trigger_actions:
        openupgrade.logged_query(
            env.cr,
            "UPDATE iot_trigger SET action = %s WHERE action = %s",
            (new, old),
        )
