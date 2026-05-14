# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade

from odoo.modules.module import get_manifest

from odoo.addons.openupgrade_scripts.apriori import renamed_modules

_logger = logging.getLogger(__name__)


def _restore_renamed_odoo_modules(env):
    """Undo the OpenUpgrade renames of Odoo modules that 18.0 still ships.

    The OpenUpgrade base pre-migration renames ``l10n_it_riba`` and
    ``spreadsheet_dashboard_purchase_stock`` to the ``_oca`` modules of its
    community repositories, while enterprise 18.0 still ships both under their
    17.0 name. A renamed row gets its name back when its ``_oca`` module is not
    installable here and the 17.0 name is, by the author of the 17.0 row; a
    database that ran a community module of that name keeps the rename. This
    runs after that pre-migration and before Odoo lists the modules and loads
    the installed ones, so the module and its xmlids go on in their 17.0 state,
    installed or not.
    """
    restored = []
    for name, oca_name in renamed_modules.items():
        env.cr.execute(
            "SELECT author FROM ir_module_module WHERE name = %s", (oca_name,)
        )
        row = env.cr.fetchone()
        if not row or get_manifest(oca_name).get("installable"):
            continue
        env.cr.execute("SELECT 1 FROM ir_module_module WHERE name = %s", (name,))
        if env.cr.fetchone():
            continue
        manifest = get_manifest(name)
        if not manifest.get("installable") or manifest.get("author") != row[0]:
            continue
        openupgrade.update_module_names(env.cr, [(oca_name, name)])
        restored.append(name)
    if restored:
        _logger.info(
            "Modules renamed by OpenUpgrade and shipped here under their 17.0 name,"
            " renamed back: %s",
            ", ".join(restored),
        )


def _uninstalled_modules_without_code(env):
    """Mark uninstalled modules that have no installable code as uninstallable.

    Runs after the base module is loaded, before the update lists the modules
    and installs the new dependencies of the installed ones. A module row of
    17.0 whose code is not on the 18.0 addons path (removed by Odoo, or renamed
    by OpenUpgrade to a community module this deployment does not ship) keeps
    its 17.0 auto-install flag and dependencies: when a dependency gets
    installed, for instance purchase, which the 18.0 account_budget requires,
    Odoo marks it 'to install' and the update ends with modules in an
    inconsistent state. Odoo cannot install such a module anyway;
    'uninstallable' is the state it gives a module without installable code,
    and the module list resets it when the code shows up. Installed modules
    are left to the module map.
    """
    env.cr.execute(
        "SELECT id, name FROM ir_module_module"
        " WHERE state = 'uninstalled' ORDER BY name"
    )
    missing = [
        (module_id, name)
        for module_id, name in env.cr.fetchall()
        if not get_manifest(name).get("installable")
    ]
    if not missing:
        return
    openupgrade.logged_query(
        env.cr,
        "UPDATE ir_module_module SET state = 'uninstallable' WHERE id IN %s",
        (tuple(module_id for module_id, _name in missing),),
    )
    _logger.info(
        "%s uninstalled modules without installable code marked uninstallable: %s",
        len(missing),
        ", ".join(name for _module_id, name in missing),
    )


@openupgrade.migrate()
def migrate(env, version):
    _restore_renamed_odoo_modules(env)
    _uninstalled_modules_without_code(env)
