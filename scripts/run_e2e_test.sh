#!/bin/bash
# =============================================================================
# OpenUpgrade Enterprise E2E runner, 17.0 -> 18.0, through the OCA framework.
#
# Builds a source database on Odoo 17.0, optionally seeds it, upgrades it with
# the Odoo 18.0 tree plus OCA openupgrade_framework (server-wide module) and
# both upgrade paths (OCA openupgrade_scripts, this repo's
# openupgrade_scripts_ee), then checks the result. Never runs git; every tree
# and venv is used read-only, and PYTHONDONTWRITEBYTECODE=1 keeps __pycache__
# out of the source trees.
#
# Phases:
#   0 preflight  validate inputs, probe both toolchains without a database
#                (17.0: odoo imported from ODOO17; 18.0: framework loaded and
#                patching Odoo, openupgradelib importable), log to
#                LOG_DIR/<db>-preflight.log
#   1 install    drop DB if present, createdb (template0, UTF8, C collation,
#                pg_trgm), install on 17.0: with BASE_SQL, first base, then
#                BASE_SQL (psql), then MODULES; without it, MODULES at once.
#                Logs LOG_DIR/<db>-install.log (and -install-base.log,
#                -base-sql.log), installed module list LOG_DIR/<db>-modules-17.txt
#   2 seed       SEED_SQL with psql, then SEED_PY through `odoo-bin shell` on
#                17.0 (the script commits itself), both optional, log to
#                LOG_DIR/<db>-seed.log; lines starting with SEEDED are echoed
#   3 upgrade    -u all on 18.0 with CONF18 at log level info, log to
#                LOG_DIR/<db>-upgrade.log
#   4 checks     modules per state, installed-module diff 17.0 vs 18.0
#                (LOG_DIR/<db>-modules-18.txt), modules in a transitional state,
#                base version, OCA legacy tables, migration script lines,
#                ERROR and CRITICAL records, optional VERIFY_SQL saved to
#                LOG_DIR/<db>-verify.log
#   5 cleanup    unless KEEP_DB=1, drop the DB and remove
#                <data_dir>/filestore/<db>; runs from an EXIT trap so it also
#                fires on failure, then prints the RESULT line
#
# Environment (defaults):
#   DB_NAME=oue18_e2e (must match ^oue18_[a-z0-9_]+$),
#   MODULES (required, comma list of 17.0 module names),
#   CONF17, CONF18 (required): odoo.conf files for the install on 17.0 and for
#     the upgrade on 18.0. CONF18 carries addons_path (odoo-v18 addons,
#     enterprise 18.0, the OCA OpenUpgrade 18.0 checkout), upgrade_path (OCA
#     openupgrade_scripts/scripts and this repo's openupgrade_scripts_ee) and
#     server_wide_modules = web,openupgrade_framework. Both must set the same
#     data_dir; database host, port, user and password come from CONF18 unless
#     DB_HOST, DB_PORT, DB_USER or DB_PASSWORD are set.
#   BASE_SQL, SEED_SQL, SEED_PY, VERIFY_SQL (optional paths), KEEP_DB=0,
#   ODOO17=/workspace/shared/worktrees/odoo-v17,
#   ODOO18=/workspace/shared/worktrees/odoo-v18,
#   VENV17=/workspace/shared/venvs/odoo-v17,
#   VENV18=/workspace/shared/venvs/odoo-v18,
#   PYLIB (optional): directory appended to PYTHONPATH after the venv
#     site-packages in every phase, for openupgradelib and the optional python
#     packages a venv lacks,
#   LOG_DIR=${TMPDIR:-/tmp}/oue18_e2e_logs,
#   DROP_DB_CMD (optional): executable called with the database name to drop
#     it; without it the runner calls dropdb itself,
#   ERROR_ALLOW_RE (optional extended regex): ERROR records of the upgrade log
#     matching it are listed as out of scope and do not fail phase 4. CRITICAL
#     records are never allowed. A validation run must pass with it unset.
#
# VERIFY_SQL contract: one row per check printed as
#   <n> PASS|FAIL|SKIP <code> <description> | <actual value>
# then "SUMMARY passed=<n> | failed=<n> | skipped=<n>". Phase 4 fails when psql
# exits non-zero, when a FAIL row is printed, when the SUMMARY line is missing
# or when its failed count differs from the FAIL rows.
#
# Usage:
#   CONF17=... CONF18=... DB_NAME=oue18_smoke MODULES=base,web \
#       scripts/run_e2e_test.sh
#
# Exit status: 0 when every phase and check passes; otherwise the code of the
# first failing phase (10 preflight, 11 install, 12 seed, 13 upgrade,
# 14 checks), or the failing command's own status for anything unexpected.
# The last line is always
#   RESULT db=<db> exit=<n> phase=<name> passed=<n> failed=<n> skipped=<n>
#          errors=<n> critical=<n> allow_re=<0|1>
# =============================================================================

set -euo pipefail

export PYTHONDONTWRITEBYTECODE=1

DB_NAME="${DB_NAME:-oue18_e2e}"
MODULES="${MODULES:-}"
CONF17="${CONF17:-}"
CONF18="${CONF18:-}"
BASE_SQL="${BASE_SQL:-}"
SEED_SQL="${SEED_SQL:-}"
SEED_PY="${SEED_PY:-}"
VERIFY_SQL="${VERIFY_SQL:-}"
KEEP_DB="${KEEP_DB:-0}"
ODOO17="${ODOO17:-/workspace/shared/worktrees/odoo-v17}"
ODOO18="${ODOO18:-/workspace/shared/worktrees/odoo-v18}"
VENV17="${VENV17:-/workspace/shared/venvs/odoo-v17}"
VENV18="${VENV18:-/workspace/shared/venvs/odoo-v18}"
PYLIB="${PYLIB:-}"
LOG_DIR="${LOG_DIR:-${TMPDIR:-/tmp}/oue18_e2e_logs}"
DROP_DB_CMD="${DROP_DB_CMD:-}"
ERROR_ALLOW_RE="${ERROR_ALLOW_RE:-}"

PREFLIGHT_LOG="${LOG_DIR}/${DB_NAME}-preflight.log"
INSTALL_BASE_LOG="${LOG_DIR}/${DB_NAME}-install-base.log"
BASE_SQL_LOG="${LOG_DIR}/${DB_NAME}-base-sql.log"
INSTALL_LOG="${LOG_DIR}/${DB_NAME}-install.log"
SEED_LOG="${LOG_DIR}/${DB_NAME}-seed.log"
UPGRADE_LOG="${LOG_DIR}/${DB_NAME}-upgrade.log"
VERIFY_LOG="${LOG_DIR}/${DB_NAME}-verify.log"
MODULES_BEFORE="${LOG_DIR}/${DB_NAME}-modules-17.txt"
MODULES_AFTER="${LOG_DIR}/${DB_NAME}-modules-18.txt"

LOG_PREFIX_RE='^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:,]+ [0-9]+ '

CLEANUP_ARMED=0
FILESTORE_DIR=""
PHASE="preflight"
R_PASSED="-"
R_FAILED="-"
R_SKIPPED="-"
R_ERRORS="-"
R_CRITICAL="-"
START_TS=$(date +%s)

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
fail() { log "FAIL: $2"; exit "$1"; }

conf_get() {
    awk -F '=' -v key="$1" '
        { k = $1; gsub(/[ \t]/, "", k) }
        k == key { v = substr($0, index($0, "=") + 1); gsub(/^[ \t]+|[ \t]+$/, "", v); print v; exit }
    ' "$2"
}

pg_db() {
    psql -X -q -At -v ON_ERROR_STOP=1 -d "${DB_NAME}" -c "$1"
}

db_exists() {
    [ "$(psql -X -q -At -d postgres -c "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'")" = "1" ]
}

db_size() {
    psql -X -q -At -d postgres -c "SELECT pg_size_pretty(pg_database_size('${DB_NAME}'))"
}

drop_database() {
    if [ -n "${DROP_DB_CMD}" ]; then
        "${DROP_DB_CMD}" "${DB_NAME}"
    else
        dropdb --if-exists --force "${DB_NAME}"
    fi
}

remove_filestore() {
    if [ -n "${FILESTORE_DIR}" ] && [ -d "${FILESTORE_DIR}" ]; then
        log "Filestore size before delete: $(du -sh "${FILESTORE_DIR}" | cut -f1)"
        if rm -r -- "${FILESTORE_DIR}"; then
            log "Deleted ${FILESTORE_DIR}"
        else
            log "WARNING: could not delete ${FILESTORE_DIR}"
        fi
    fi
}

on_exit() {
    local rc=$?
    set +e
    if [ "${CLEANUP_ARMED}" = "1" ]; then
        log "Phase 5: cleanup (KEEP_DB=${KEEP_DB})"
        if [ "${KEEP_DB}" = "1" ]; then
            if db_exists; then
                log "KEEP_DB=1: keeping ${DB_NAME}, size $(db_size)"
            fi
            log "KEEP_DB=1: keeping ${FILESTORE_DIR}"
        else
            if db_exists; then
                log "DB size before drop: ${DB_NAME} $(db_size)"
                if drop_database; then
                    log "Dropped database ${DB_NAME}"
                else
                    log "WARNING: could not drop ${DB_NAME}"
                fi
            else
                log "Database ${DB_NAME} not present, nothing to drop"
            fi
            remove_filestore
        fi
    fi
    if [ -d "${LOG_DIR}" ]; then
        log "Log directory size: $(du -sh "${LOG_DIR}" | cut -f1) ${LOG_DIR}"
    fi
    log "Total time: $(( $(date +%s) - START_TS ))s, exit status ${rc}"
    if [ "${rc}" -eq 0 ]; then
        PHASE="passed"
    fi
    printf 'RESULT db=%s exit=%s phase=%s passed=%s failed=%s skipped=%s errors=%s critical=%s allow_re=%s\n' \
        "${DB_NAME}" "${rc}" "${PHASE}" "${R_PASSED}" "${R_FAILED}" "${R_SKIPPED}" "${R_ERRORS}" "${R_CRITICAL}" \
        "$([ -n "${ERROR_ALLOW_RE}" ] && echo 1 || echo 0)"
    exit "${rc}"
}

trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

site_packages() {
    "$1/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])'
}

phase0_preflight() {
    PHASE="preflight"
    log "Phase 0: preflight"
    [[ "${DB_NAME}" =~ ^oue18_[a-z0-9_]+$ ]] || fail 10 "DB_NAME '${DB_NAME}' must match ^oue18_[a-z0-9_]+$"
    [ -n "${MODULES}" ] || fail 10 "MODULES is required (comma list of 17.0 names, e.g. base,web)"
    [[ "${MODULES}" =~ ^[a-z0-9_]+(,[a-z0-9_]+)*$ ]] || fail 10 "MODULES '${MODULES}' is not a plain comma list"
    [ -n "${CONF17}" ] || fail 10 "CONF17 is required (odoo.conf for the 17.0 install)"
    [ -n "${CONF18}" ] || fail 10 "CONF18 is required (odoo.conf for the 18.0 upgrade)"
    local f
    for f in "${CONF17}" "${CONF18}" "${ODOO17}/odoo-bin" "${ODOO18}/odoo-bin" "${VENV17}/bin/python" "${VENV18}/bin/python"; do
        [ -e "${f}" ] || fail 10 "missing ${f}"
    done
    for f in "${BASE_SQL}" "${SEED_SQL}" "${SEED_PY}" "${VERIFY_SQL}"; do
        [ -z "${f}" ] || [ -f "${f}" ] || fail 10 "missing ${f}"
    done
    [ -z "${DROP_DB_CMD}" ] || [ -x "${DROP_DB_CMD}" ] || fail 10 "DROP_DB_CMD ${DROP_DB_CMD} is not executable"
    [ -z "${PYLIB}" ] || [ -d "${PYLIB}" ] || fail 10 "PYLIB ${PYLIB} is not a directory"
    [ -n "$(conf_get server_wide_modules "${CONF18}")" ] || fail 10 "CONF18 sets no server_wide_modules"
    [ -n "$(conf_get upgrade_path "${CONF18}")" ] || fail 10 "CONF18 sets no upgrade_path"
    local data17 data18
    data17=$(conf_get data_dir "${CONF17}")
    data18=$(conf_get data_dir "${CONF18}")
    [ -n "${data18}" ] || fail 10 "CONF18 sets no data_dir"
    [ "${data17}" = "${data18}" ] || fail 10 "data_dir differs: CONF17 '${data17}', CONF18 '${data18}'"
    FILESTORE_DIR="${data18}/filestore/${DB_NAME}"
    mkdir -p "${LOG_DIR}"
    rm -f -- "${INSTALL_BASE_LOG}" "${BASE_SQL_LOG}" "${INSTALL_LOG}" "${SEED_LOG}" "${UPGRADE_LOG}" \
        "${VERIFY_LOG}" "${MODULES_BEFORE}" "${MODULES_AFTER}"

    export PGHOST="${DB_HOST:-$(conf_get db_host "${CONF18}")}"
    export PGPORT="${DB_PORT:-$(conf_get db_port "${CONF18}")}"
    export PGUSER="${DB_USER:-$(conf_get db_user "${CONF18}")}"
    export PGPASSWORD="${DB_PASSWORD:-$(conf_get db_password "${CONF18}")}"

    INSTALL_PYTHONPATH="$(site_packages "${VENV17}")${PYLIB:+:${PYLIB}}"
    UPGRADE_PYTHONPATH="$(site_packages "${VENV18}")${PYLIB:+:${PYLIB}}"

    log "DB_NAME=${DB_NAME} MODULES=${MODULES} KEEP_DB=${KEEP_DB}"
    log "BASE_SQL=${BASE_SQL:-<unset>} SEED_SQL=${SEED_SQL:-<unset>} SEED_PY=${SEED_PY:-<unset>} VERIFY_SQL=${VERIFY_SQL:-<unset>}"
    log "17.0: ${VENV17}/bin/python ${ODOO17}/odoo-bin -c ${CONF17} (tree $(git -C "${ODOO17}" rev-parse --short=12 HEAD 2>/dev/null || echo n/a))"
    log "18.0: ${VENV18}/bin/python ${ODOO18}/odoo-bin -c ${CONF18} (tree $(git -C "${ODOO18}" rev-parse --short=12 HEAD 2>/dev/null || echo n/a))"
    log "17.0 addons_path: $(conf_get addons_path "${CONF17}")"
    log "18.0 addons_path: $(conf_get addons_path "${CONF18}")"
    log "18.0 upgrade_path: $(conf_get upgrade_path "${CONF18}")"
    log "18.0 server_wide_modules: $(conf_get server_wide_modules "${CONF18}")"
    log "install PYTHONPATH=${INSTALL_PYTHONPATH}"
    log "upgrade PYTHONPATH=${UPGRADE_PYTHONPATH}"
    log "filestore ${FILESTORE_DIR}; drop with ${DROP_DB_CMD:-dropdb}"
    log "PostgreSQL ${PGUSER}@${PGHOST}:${PGPORT}; logs in ${LOG_DIR}"

    local rc=0
    PYTHONPATH="${INSTALL_PYTHONPATH}" "${VENV17}/bin/python" "${ODOO17}/odoo-bin" shell \
        -c "${CONF17}" --no-http --log-level=warn > "${PREFLIGHT_LOG}" 2>&1 <<'PY' || rc=$?
import odoo
print("PROBE17 odoo=%s %s" % (odoo.release.version, odoo.__file__))
PY
    [ "${rc}" -eq 0 ] || fail 10 "17.0 toolchain probe exited ${rc}, see ${PREFLIGHT_LOG}"
    grep -q "^PROBE17 odoo=17\.0.* ${ODOO17}/odoo/__init__.py$" "${PREFLIGHT_LOG}" || fail 10 "17.0 odoo not imported from ${ODOO17}, see ${PREFLIGHT_LOG}"

    rc=0
    PYTHONPATH="${UPGRADE_PYTHONPATH}" "${VENV18}/bin/python" "${ODOO18}/odoo-bin" shell \
        -c "${CONF18}" --no-http --log-level=warn >> "${PREFLIGHT_LOG}" 2>&1 <<'PY' || rc=$?
import importlib.metadata
import sys
import lxml
import odoo
import openupgradelib
from odoo.modules.migration import MigrationManager
from odoo.addons.base.models.ir_model import IrModelFields
print("PROBE18 odoo=%s %s" % (odoo.release.version, odoo.__file__))
print("PROBE18 framework_module_loaded=%s" % ("odoo.addons.openupgrade_framework" in sys.modules))
print("PROBE18 migration_get_files_from=%s" % MigrationManager._get_files.__module__)
print("PROBE18 drop_column_from=%s" % IrModelFields._drop_column.__module__)
print("PROBE18 openupgradelib=%s %s" % (importlib.metadata.version("openupgradelib"), openupgradelib.__file__))
print("PROBE18 lxml=%s %s" % (lxml.__version__, lxml.__file__))
print("PROBE18 server_wide_modules=%s" % ",".join(odoo.conf.server_wide_modules))
print("PROBE18 upgrade_path=%s" % odoo.tools.config["upgrade_path"])
PY
    grep -E '^PROBE1[78] ' "${PREFLIGHT_LOG}" | sed 's/^/    /' || true
    [ "${rc}" -eq 0 ] || fail 10 "18.0 toolchain probe exited ${rc}, see ${PREFLIGHT_LOG}"
    grep -q "^PROBE18 odoo=18\.0.* ${ODOO18}/odoo/__init__.py$" "${PREFLIGHT_LOG}" || fail 10 "18.0 odoo not imported from ${ODOO18}, see ${PREFLIGHT_LOG}"
    grep -q '^PROBE18 framework_module_loaded=True$' "${PREFLIGHT_LOG}" || fail 10 "openupgrade_framework not loaded, see ${PREFLIGHT_LOG}"
    grep -q '^PROBE18 migration_get_files_from=odoo.addons.openupgrade_framework' "${PREFLIGHT_LOG}" || fail 10 "framework patches not applied, see ${PREFLIGHT_LOG}"
    psql -X -q -At -d postgres -c "SELECT 1" > /dev/null || fail 10 "cannot reach PostgreSQL at ${PGHOST}:${PGPORT} as ${PGUSER}"
    log "Phase 0 OK: 17.0 and 18.0 toolchains resolve, framework patches Odoo 18, openupgradelib importable, PostgreSQL reachable"
}

odoo17() {
    local command=()
    if [ "$#" -gt 0 ] && [ "${1#-}" = "$1" ]; then
        command=("$1")
        shift
    fi
    PYTHONPATH="${INSTALL_PYTHONPATH}" "${VENV17}/bin/python" "${ODOO17}/odoo-bin" "${command[@]}" \
        -c "${CONF17}" -d "${DB_NAME}" "$@"
}

phase1_install() {
    PHASE="install"
    log "Phase 1: create ${DB_NAME} and install ${MODULES} on 17.0"
    CLEANUP_ARMED=1
    if db_exists; then
        log "Dropping existing ${DB_NAME}"
        drop_database
    fi
    if [ -d "${FILESTORE_DIR}" ]; then
        log "Removing stale ${FILESTORE_DIR}"
        rm -r -- "${FILESTORE_DIR}"
    fi
    createdb -T template0 -E UTF8 --lc-collate=C "${DB_NAME}"
    pg_db "CREATE EXTENSION IF NOT EXISTS pg_trgm" > /dev/null
    log "Created ${DB_NAME}"

    local t0 rc=0
    if [ -n "${BASE_SQL}" ]; then
        t0=$(date +%s)
        odoo17 -i base --stop-after-init --no-http > "${INSTALL_BASE_LOG}" 2>&1 || rc=$?
        log "17.0 base install exit ${rc} after $(( $(date +%s) - t0 ))s, log ${INSTALL_BASE_LOG}"
        if [ "${rc}" -ne 0 ]; then
            tail -n 30 "${INSTALL_BASE_LOG}" | sed 's/^/    /'
            fail 11 "base install on 17.0 failed"
        fi
        psql -X -v ON_ERROR_STOP=1 -d "${DB_NAME}" -f "${BASE_SQL}" > "${BASE_SQL_LOG}" 2>&1 || rc=$?
        if [ "${rc}" -ne 0 ]; then
            tail -n 20 "${BASE_SQL_LOG}" | sed 's/^/    /'
            fail 11 "BASE_SQL failed (exit ${rc}), log ${BASE_SQL_LOG}"
        fi
        log "BASE_SQL OK, log ${BASE_SQL_LOG}"
    fi
    t0=$(date +%s)
    odoo17 -i "${MODULES}" --stop-after-init --no-http > "${INSTALL_LOG}" 2>&1 || rc=$?
    log "17.0 install exit ${rc} after $(( $(date +%s) - t0 ))s, log ${INSTALL_LOG}"
    if [ "${rc}" -ne 0 ]; then
        tail -n 30 "${INSTALL_LOG}" | sed 's/^/    /'
        fail 11 "install on 17.0 failed"
    fi
    pg_db "SELECT name FROM ir_module_module WHERE state = 'installed' ORDER BY name COLLATE \"C\"" > "${MODULES_BEFORE}"
    log "Installed modules: $(wc -l < "${MODULES_BEFORE}"), base $(pg_db "SELECT latest_version FROM ir_module_module WHERE name = 'base'"), list ${MODULES_BEFORE}"
    local missing
    missing=$(pg_db "SELECT string_agg(m, ',') FROM unnest(string_to_array('${MODULES}', ',')) AS m WHERE m NOT IN (SELECT name FROM ir_module_module WHERE state = 'installed')")
    [ -z "${missing}" ] || fail 11 "requested modules not installed: ${missing}"
}

phase2_seed() {
    PHASE="seed"
    if [ -z "${SEED_SQL}" ] && [ -z "${SEED_PY}" ]; then
        log "Phase 2: seed skipped (SEED_SQL and SEED_PY unset)"
        return 0
    fi
    : > "${SEED_LOG}"
    local rc=0
    if [ -n "${SEED_SQL}" ]; then
        log "Phase 2: seeding from ${SEED_SQL}"
        psql -X -v ON_ERROR_STOP=1 -d "${DB_NAME}" -f "${SEED_SQL}" >> "${SEED_LOG}" 2>&1 || rc=$?
        if [ "${rc}" -ne 0 ]; then
            tail -n 20 "${SEED_LOG}" | sed 's/^/    /'
            fail 12 "seed SQL failed (exit ${rc}), log ${SEED_LOG}"
        fi
    fi
    if [ -n "${SEED_PY}" ]; then
        log "Phase 2: seeding from ${SEED_PY} through odoo-bin shell on 17.0"
        odoo17 shell --no-http --log-level=warn < "${SEED_PY}" >> "${SEED_LOG}" 2>&1 || rc=$?
        if [ "${rc}" -ne 0 ]; then
            tail -n 30 "${SEED_LOG}" | sed 's/^/    /'
            fail 12 "seed script failed (exit ${rc}), log ${SEED_LOG}"
        fi
    fi
    grep -E '^SEEDED ' "${SEED_LOG}" | sed 's/^/    /' || true
    log "Seed OK, log ${SEED_LOG}"
}

phase3_upgrade() {
    PHASE="upgrade"
    log "Phase 3: upgrade ${DB_NAME} on 18.0 with openupgrade_framework (-u all)"
    local t0 rc=0
    t0=$(date +%s)
    PYTHONPATH="${UPGRADE_PYTHONPATH}" "${VENV18}/bin/python" "${ODOO18}/odoo-bin" -c "${CONF18}" -d "${DB_NAME}" \
        -u all --stop-after-init --no-http --log-level=info > "${UPGRADE_LOG}" 2>&1 || rc=$?
    log "18.0 upgrade exit ${rc} after $(( $(date +%s) - t0 ))s, log ${UPGRADE_LOG} ($(du -h "${UPGRADE_LOG}" | cut -f1))"
    count_log_records
    if [ "${rc}" -ne 0 ]; then
        grep -n -E "${LOG_PREFIX_RE}(ERROR|CRITICAL) " "${UPGRADE_LOG}" | head -n 10 | cut -c1-300 | sed 's/^/    /' || true
        tail -n 40 "${UPGRADE_LOG}" | sed 's/^/    /'
        fail 13 "upgrade on 18.0 failed"
    fi
}

count_log_records() {
    R_ERRORS=$(grep -c -E "${LOG_PREFIX_RE}ERROR " "${UPGRADE_LOG}" || true)
    R_CRITICAL=$(grep -c -E "${LOG_PREFIX_RE}CRITICAL " "${UPGRADE_LOG}" || true)
}

run_verify() {
    local vrc=0 summary rows_failed
    psql -X -v ON_ERROR_STOP=1 -d "${DB_NAME}" -f "${VERIFY_SQL}" > "${VERIFY_LOG}" 2>&1 || vrc=$?
    log "VERIFY_SQL ${VERIFY_SQL} exit ${vrc}, output ${VERIFY_LOG}"
    rows_failed=$(grep -c -E '^ *[0-9]+ FAIL ' "${VERIFY_LOG}" || true)
    summary=$(grep -E '^SUMMARY passed=[0-9]+ \| failed=[0-9]+ \| skipped=[0-9]+' "${VERIFY_LOG}" | tail -n 1 || true)
    if [ -n "${summary}" ]; then
        R_PASSED=$(sed -E 's/^SUMMARY passed=([0-9]+).*/\1/' <<< "${summary}")
        R_FAILED=$(sed -E 's/^SUMMARY passed=[0-9]+ \| failed=([0-9]+).*/\1/' <<< "${summary}")
        R_SKIPPED=$(sed -E 's/^SUMMARY .*skipped=([0-9]+).*/\1/' <<< "${summary}")
        log "Verify: ${summary}"
    else
        R_FAILED="${rows_failed}"
        log "Verify printed no SUMMARY line"
    fi
    if [ "${rows_failed}" -ne 0 ]; then
        log "FAIL rows:"
        grep -E '^ *[0-9]+ FAIL ' "${VERIFY_LOG}" | head -n 40 | cut -c1-300 | sed 's/^/    /'
    fi
    [ "${vrc}" -eq 0 ] && [ -n "${summary}" ] && [ "${rows_failed}" -eq 0 ] && [ "${R_FAILED}" = "${rows_failed}" ]
}

phase4_checks() {
    PHASE="checks"
    log "Phase 4: checks"
    local problems=0

    log "Modules per state:"
    pg_db "SELECT state || ': ' || count(*) FROM ir_module_module GROUP BY state ORDER BY state" | sed 's/^/    /'

    pg_db "SELECT name FROM ir_module_module WHERE state = 'installed' ORDER BY name COLLATE \"C\"" > "${MODULES_AFTER}"
    log "Installed on 17.0 but not on 18.0 (renamed, merged or lost): $(LC_ALL=C comm -23 "${MODULES_BEFORE}" "${MODULES_AFTER}" | paste -sd ' ' -)"
    log "Installed on 18.0 but not on 17.0 (new, renamed targets, auto_install): $(LC_ALL=C comm -13 "${MODULES_BEFORE}" "${MODULES_AFTER}" | paste -sd ' ' -)"

    local bad bad_count
    bad=$(pg_db "SELECT name || ' (' || state || ')' FROM ir_module_module WHERE state NOT IN ('installed', 'uninstalled', 'uninstallable') ORDER BY name")
    bad_count=$(pg_db "SELECT count(*) FROM ir_module_module WHERE state NOT IN ('installed', 'uninstalled', 'uninstallable')")
    log "Modules in an inconsistent state: ${bad_count}"
    if [ "${bad_count}" -ne 0 ]; then
        printf '%s\n' "${bad}" | sed 's/^/    /'
        problems=$((problems + 1))
    fi

    local base_version
    base_version=$(pg_db "SELECT latest_version FROM ir_module_module WHERE name = 'base'")
    log "base version: ${base_version}"
    if [[ "${base_version}" != 18.0.* ]]; then
        log "base is not on 18.0"
        problems=$((problems + 1))
    fi

    log "OCA legacy tables (openupgrade_legacy_18_0_*): $(pg_db "SELECT count(*) FROM pg_tables WHERE starts_with(tablename, 'openupgrade_legacy_18_0_')")"
    pg_db "SELECT tablename FROM pg_tables WHERE starts_with(tablename, 'openupgrade_legacy_18_0_') ORDER BY tablename LIMIT 20" | sed 's/^/    /'

    log "Migration script executions logged: $(grep -c -E ': Running (migration|upgrade) ' "${UPGRADE_LOG}" || true); base:"
    grep -E 'module base: Running (migration|upgrade) ' "${UPGRADE_LOG}" | sed -E 's/^.* (module base: )/    \1/' || true
    log "OpenUpgrade logger lines: $(grep -c -E ' OpenUpgrade: ' "${UPGRADE_LOG}" || true)"

    local swm_fail
    swm_fail=$(grep -c 'Failed to load server-wide module' "${UPGRADE_LOG}" || true)
    log "Server-wide module load failures: ${swm_fail}"
    [ "${swm_fail}" -eq 0 ] || problems=$((problems + 1))

    local err_count allowed_count raw_count
    count_log_records
    err_count="${R_ERRORS}"
    raw_count=$(grep -c -E 'ERROR|CRITICAL' "${UPGRADE_LOG}" || true)
    log "Upgrade log: ${R_ERRORS} ERROR, ${R_CRITICAL} CRITICAL records (${raw_count} lines containing either word anywhere)"
    allowed_count=0
    if [ -n "${ERROR_ALLOW_RE}" ] && [ "${err_count}" -ne 0 ]; then
        allowed_count=$(grep -E "${LOG_PREFIX_RE}ERROR " "${UPGRADE_LOG}" | grep -c -E "${ERROR_ALLOW_RE}" || true)
        err_count=$((err_count - allowed_count))
        log "ERROR records matching ERROR_ALLOW_RE (out of scope, listed below): ${allowed_count}"
        grep -n -E "${LOG_PREFIX_RE}ERROR " "${UPGRADE_LOG}" | grep -E "${ERROR_ALLOW_RE}" | head -n 20 | cut -c1-220 | sed 's/^/    allowed: /' || true
    fi
    if [ $((err_count + R_CRITICAL)) -ne 0 ]; then
        log "First 20 unallowed ERROR records, then the CRITICAL records:"
        if [ -n "${ERROR_ALLOW_RE}" ]; then
            grep -n -E "${LOG_PREFIX_RE}ERROR " "${UPGRADE_LOG}" | grep -v -E "${ERROR_ALLOW_RE}" | head -n 20 | cut -c1-300 | sed 's/^/    /' || true
        else
            grep -n -E "${LOG_PREFIX_RE}ERROR " "${UPGRADE_LOG}" | head -n 20 | cut -c1-300 | sed 's/^/    /' || true
        fi
        grep -n -E "${LOG_PREFIX_RE}CRITICAL " "${UPGRADE_LOG}" | head -n 10 | cut -c1-300 | sed 's/^/    /' || true
        problems=$((problems + 1))
    fi

    log "Config warnings in upgrade log:"
    grep -E ' WARNING [^ ]+ odoo\.tools\.config: |since 18\.0' "${UPGRADE_LOG}" | sed 's/^/    /' || true

    if [ -n "${VERIFY_SQL}" ]; then
        run_verify || problems=$((problems + 1))
    else
        log "VERIFY_SQL unset, skipped"
    fi

    [ "${problems}" -eq 0 ] || fail 14 "${problems} check(s) failed"
    log "Phase 4 OK"
}

log "OpenUpgrade Enterprise E2E 17.0 -> 18.0 (framework)"
phase0_preflight
phase1_install
phase2_seed
phase3_upgrade
phase4_checks
log "All phases passed"
