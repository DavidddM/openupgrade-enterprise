# OpenUpgrade Scripts for Odoo Enterprise

Migration scripts for upgrading Odoo Enterprise modules from v17 to v18, following [OpenUpgrade](https://github.com/OCA/OpenUpgrade) conventions.

> **Note:** These scripts require a valid Odoo Enterprise subscription. This repository contains only migration logic, not Odoo source code.

## Covered Modules

| Module | Description |
|--------|-------------|
| `account_accountant` | Accounting dashboard, field renames, new `accountant` dependency |
| `account_iso20022` | Renamed from `account_sepa` |
| `account_reports` | P&L restructuring, footnote→annotation rename, expression engine changes |
| `l10n_de_reports` | DATEV identifier fields → company-dependent (INTEGER→JSONB) |
| `base` | Module rename: `account_sepa` → `account_iso20022` |

## Requirements

```bash
pip install openupgradelib
```

## Usage

Add this repository's scripts folder to your `--upgrade-path`:

```bash
odoo-bin \
    --upgrade-path=/path/to/openupgrade_scripts/scripts,/path/to/openupgrade-enterprise/openupgrade_scripts_ee \
    -d your_database \
    -u all \
    --stop-after-init
```

## License

AGPL-3.0
