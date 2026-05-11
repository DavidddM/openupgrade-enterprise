#!/bin/bash
# =============================================================================
# OpenUpgrade Enterprise E2E batches, 17.0 -> 18.0, without demo data.
#
# Runs scripts/run_e2e_test.sh once per batch, one database at a time
# (oue18_batch_<name>), and prints one row per batch at the end: runner exit,
# failing phase, verify checks passed / failed / skipped, ERROR and CRITICAL
# records of the upgrade log, time and runner log. Every module that has a
# script under openupgrade_scripts_ee is installed by at least one batch;
# l10n_mx_edi, l10n_ec_edi, l10n_pe_edi and mrp_plm, whose certificate and
# document many2one fields change comodel, only by the crit batches.
#
# Batches (MODULES use 17.0 module names, account_sepa is the 17.0 name of
# account_iso20022):
#   acc       accounting: accountant, reports, assets (+fleet), budget (+project),
#             SEPA credit transfer and direct debit, inter-company rules
#   hr        payroll core, appraisal (+survey), salary configurator, referral,
#             planning, forecast
#   prod      documents, spreadsheet, studio, WhatsApp, VoIP, IoT, approvals,
#             social marketing (all networks), MPS
#   svc       appointment (+crm), frontdesk, helpdesk (+timesheet billing),
#             field service report, worksheet, timesheet billing, subscription,
#             rental (+stock, +website), eCommerce dashboard, Sendcloud, FedEx
#   l10n      DE reports, BE CodaBox, AR, CL and NL certificate localizations
#   pay       AU, BE, CH and KE payroll
#   crit      l10n_mx_edi, l10n_ec_edi, l10n_pe_edi, mrp_plm together
#   crit_mx, crit_ec, crit_pe, crit_plm   the same modules one per database
#   Each list can be overridden with BATCH_<NAME> (upper case), e.g. BATCH_HR.
#
# Usage:
#   CONF17=... CONF18=... scripts/run_e2e_batches.sh         runs BATCHES
#   CONF17=... CONF18=... scripts/run_e2e_batches.sh hr crit runs the named ones
#
# Environment (defaults):
#   BATCHES="acc hr prod svc l10n pay crit", KEEP_DB=0, RUN_TAG (optional,
#   appended to the runner log name and to copies of the per-phase logs, so
#   several attempts keep their evidence), ERROR_ALLOW_RE (optional, passed to
#   the runner; the table then marks the rows, which are not a validation run),
#   RUNNER=<this directory>/run_e2e_test.sh,
#   BASE_SQL=<this directory>/seed_companies.sql,
#   SEED_SQL=<this directory>/seed_test_data.sql,
#   SEED_PY (unset), VERIFY_SQL=<this directory>/verify_migration.sql;
#   BASE_SQL, SEED_SQL, SEED_PY and VERIFY_SQL set to an empty value disable
#   that step. LOG_DIR=${TMPDIR:-/tmp}/oue18_e2e_logs. CONF17, CONF18, PYLIB,
#   DROP_DB_CMD, ODOO17, ODOO18, VENV17, VENV18 and DB_* are passed to the
#   runner unchanged.
#
# Exit status: 0 when every batch exits 0, 1 otherwise, 2 on an unknown batch.
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="${RUNNER:-${SCRIPT_DIR}/run_e2e_test.sh}"
BASE_SQL="${BASE_SQL-${SCRIPT_DIR}/seed_companies.sql}"
SEED_SQL="${SEED_SQL-${SCRIPT_DIR}/seed_test_data.sql}"
SEED_PY="${SEED_PY-}"
VERIFY_SQL="${VERIFY_SQL-${SCRIPT_DIR}/verify_migration.sql}"
LOG_DIR="${LOG_DIR:-${TMPDIR:-/tmp}/oue18_e2e_logs}"
KEEP_DB="${KEEP_DB:-0}"
RUN_TAG="${RUN_TAG:-}"
ERROR_ALLOW_RE="${ERROR_ALLOW_RE:-}"
BATCHES="${BATCHES:-acc hr prod svc l10n pay crit}"

BATCH_ACC="${BATCH_ACC:-account_accountant,account_reports,account_asset,account_asset_fleet,account_budget,project_account_budget,account_sepa,account_sepa_direct_debit,account_inter_company_rules,sale_purchase_inter_company_rules}"
BATCH_HR="${BATCH_HR:-hr_payroll,hr_appraisal,hr_appraisal_survey,hr_contract_salary,hr_referral,planning,project_forecast}"
BATCH_PROD="${BATCH_PROD:-documents,spreadsheet_edition,web_studio,whatsapp,voip,iot,approvals,social,social_facebook,social_instagram,social_linkedin,social_push_notifications,social_twitter,mrp_mps}"
BATCH_SVC="${BATCH_SVC:-appointment,appointment_crm,frontdesk,helpdesk,helpdesk_sale_timesheet,industry_fsm_report,worksheet,sale_timesheet_enterprise,sale_subscription,sale_renting,sale_stock_renting,website_sale_renting,website_sale_dashboard,website_delivery_sendcloud,website_sale_fedex}"
BATCH_L10N="${BATCH_L10N:-l10n_de_reports,l10n_be_codabox,l10n_ar_edi,l10n_cl_edi,l10n_nl_reports_sbr}"
BATCH_PAY="${BATCH_PAY:-l10n_au_hr_payroll,l10n_be_hr_payroll,l10n_ch_hr_payroll,l10n_ke_hr_payroll}"
BATCH_CRIT_MX="${BATCH_CRIT_MX:-l10n_mx_edi}"
BATCH_CRIT_EC="${BATCH_CRIT_EC:-l10n_ec_edi}"
BATCH_CRIT_PE="${BATCH_CRIT_PE:-l10n_pe_edi}"
BATCH_CRIT_PLM="${BATCH_CRIT_PLM:-mrp_plm}"
BATCH_CRIT="${BATCH_CRIT:-${BATCH_CRIT_MX},${BATCH_CRIT_EC},${BATCH_CRIT_PE},${BATCH_CRIT_PLM}}"

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

batch_modules() {
    local var="BATCH_${1^^}"
    printf '%s' "${!var:-}"
}

phase_of() {
    case "$1" in
        0) echo "passed" ;;
        10) echo "preflight" ;;
        11) echo "install" ;;
        12) echo "seed" ;;
        13) echo "upgrade" ;;
        14) echo "checks" ;;
        *) echo "other" ;;
    esac
}

result_field() {
    local line="$1" key="$2" value
    value=$(sed -n -E "s/.* ${key}=([^ ]+).*/\1/p" <<< " ${line}")
    printf '%s' "${value:--}"
}

if [ "$#" -gt 0 ]; then
    BATCHES="$*"
fi

for name in ${BATCHES}; do
    if [[ ! "${name}" =~ ^[a-z0-9_]+$ ]] || [ -z "$(batch_modules "${name}")" ]; then
        log "unknown batch '${name}'"
        exit 2
    fi
done

mkdir -p "${LOG_DIR}"
declare -a ROWS=()
overall=0
allow_flag=""
[ -z "${ERROR_ALLOW_RE}" ] || allow_flag=" (ERROR_ALLOW_RE set)"

for name in ${BATCHES}; do
    db="oue18_batch_${name}"
    modules="$(batch_modules "${name}")"
    suffix="${RUN_TAG:+-${RUN_TAG}}"
    runner_log="${LOG_DIR}/${db}-runner${suffix}.log"
    log "batch ${name}: ${db}, $(tr ',' '\n' <<< "${modules}" | wc -l) modules, runner log ${runner_log}"
    t0=$(date +%s)
    env DB_NAME="${db}" MODULES="${modules}" BASE_SQL="${BASE_SQL}" SEED_SQL="${SEED_SQL}" SEED_PY="${SEED_PY}" \
        VERIFY_SQL="${VERIFY_SQL}" KEEP_DB="${KEEP_DB}" LOG_DIR="${LOG_DIR}" ERROR_ALLOW_RE="${ERROR_ALLOW_RE}" \
        bash "${RUNNER}" > "${runner_log}" 2>&1
    rc=$?
    elapsed=$(( $(date +%s) - t0 ))
    result=$(grep -E '^RESULT ' "${runner_log}" | tail -n 1)
    if [ -n "${RUN_TAG}" ]; then
        for kind in preflight install-base base-sql install seed upgrade verify modules-17.txt modules-18.txt; do
            case "${kind}" in
                *.txt) src="${LOG_DIR}/${db}-${kind}"; dst="${LOG_DIR}/${db}${suffix}-${kind}" ;;
                *) src="${LOG_DIR}/${db}-${kind}.log"; dst="${LOG_DIR}/${db}${suffix}-${kind}.log" ;;
            esac
            [ -f "${src}" ] && cp -- "${src}" "${dst}"
        done
    fi
    checks="$(result_field "${result}" passed) | $(result_field "${result}" failed) | $(result_field "${result}" skipped)"
    records="$(result_field "${result}" errors) / $(result_field "${result}" critical)"
    log "batch ${name}: runner exit ${rc} ($(phase_of "${rc}")) after ${elapsed}s, checks passed | failed | skipped: ${checks}, ERROR / CRITICAL: ${records}${allow_flag}"
    tail -n 25 "${runner_log}" | sed 's/^/    /'
    ROWS+=("$(printf '%-8s | %-22s | %4s | %-9s | %-16s | %-9s | %5ss | %s%s' "${name}" "${db}" "${rc}" "$(phase_of "${rc}")" "${checks}" "${records}" "${elapsed}" "${runner_log}" "${allow_flag}")")
    [ "${rc}" -eq 0 ] || overall=1
done

echo
echo "batch    | database               | exit | phase     | pass | fail | skip | err / crit |  time  | runner log"
echo "---------+------------------------+------+-----------+------------------+-----------+--------+-----------"
for row in "${ROWS[@]}"; do
    echo "${row}"
done
exit "${overall}"
