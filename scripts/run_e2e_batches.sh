#!/bin/bash
# =============================================================================
# OpenUpgrade Enterprise E2E batches, 17.0 -> 18.0, without demo data.
#
# Runs scripts/run_e2e_test.sh once per batch, one database at a time
# (oue18_batch_<name>): install the batch on 17.0, seed it with
# scripts/seed_v17.py, upgrade it to 18.0 and check it with
# scripts/verify_v18.sql. Prints one row per batch at the end: runner exit,
# failing phase, checks passed / failed / skipped, ERROR and CRITICAL records
# of the upgrade log, time and runner log.
#
# Every module with a script under openupgrade_scripts_ee is installed,
# seeded and checked by at least one batch (base by all of them). Each seed
# block runs when its module is installed and each check skips when its
# module is not, so a batch that pulls in more modules than it names seeds
# and checks those too.
#
# Batches (MODULES use 17.0 names: account_sepa, hr_payroll_account_sepa and
# l10n_au_keypay are account_iso20022, hr_payroll_account_iso20022 and
# l10n_employment_hero in 18.0):
#   acc      accounting: accountant, reports, assets (+fleet), budget
#            (+project), SEPA credit transfer and direct debit, inter-company
#            rules (invoices, orders), follow-up, DATEV
#   hr       payroll (+accounting, +SEPA), appraisal (+survey), salary
#            configurator, referral, CV digitization, planning, forecast
#   pay      AU payroll (+accounting, Employment Hero), BE, CH, KE and LU
#            payroll
#   prod     documents, spreadsheet, studio, WhatsApp, VoIP, approvals, sign,
#            IoT, MPS, work order IoT, PLM
#   mkt      social marketing: Facebook, Instagram, LinkedIn, push
#            notifications, X
#   svc      appointment (+CRM), frontdesk, helpdesk (+timesheet billing),
#            field service report (+sale), worksheet, timesheet leaderboard
#   sale     subscription, rental (+stock, +sign, +website), eCommerce
#            dashboard, Sendcloud, FedEx, Pricer, restaurant appointments,
#            preparation display, purchase dashboards
#   sale_mi  Sendcloud and FedEx again, in a database whose name ends in _mi:
#            the seed selects imperial units there
#   edi      the certificate localizations together: AR, CL, MX, EC, PE, NL
#            SBR and BE payroll (accounting installed on 17.0)
#   edi_inv  EC and PE on an invoicing database: 18.0 installs
#            account_accountant during the upgrade and reloads their charts
#   l10n     merged and renamed localizations: MX stock (3.0, 3.1, foreign
#            trade), BR services, IT Ri.Ba., BE CodaBox, IN GST returns
#   rem      modules 18.0 removed or folded: TaxCloud and its six bridges,
#            eBay, customer statements (+UK), BE/US consolidation demo, DK
#            EDI, FR VAT reimbursement, subcontracting Studio, Twitter walls
#   Each list can be overridden with BATCH_<NAME> (upper case), e.g. BATCH_HR,
#   and any other name runs when its BATCH_<NAME> is set.
#
# Usage:
#   CONF17=... CONF18=... scripts/run_e2e_batches.sh         runs BATCHES
#   CONF17=... CONF18=... scripts/run_e2e_batches.sh hr edi  runs the named ones
#
# Environment (defaults):
#   BATCHES (every batch above), KEEP_DB=0, RUN_TAG (optional, appended to the
#   runner log name and to copies of the per-phase logs, so several attempts
#   keep their evidence), ERROR_ALLOW_RE (optional, passed to the runner; the
#   table then marks the rows, which are not a validation run),
#   RUNNER=<this directory>/run_e2e_test.sh,
#   SEED_PY=<this directory>/seed_v17.py,
#   VERIFY_SQL=<this directory>/verify_v18.sql,
#   BASE_SQL and SEED_SQL (unset);
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
BASE_SQL="${BASE_SQL-}"
SEED_SQL="${SEED_SQL-}"
SEED_PY="${SEED_PY-${SCRIPT_DIR}/seed_v17.py}"
VERIFY_SQL="${VERIFY_SQL-${SCRIPT_DIR}/verify_v18.sql}"
LOG_DIR="${LOG_DIR:-${TMPDIR:-/tmp}/oue18_e2e_logs}"
KEEP_DB="${KEEP_DB:-0}"
RUN_TAG="${RUN_TAG:-}"
ERROR_ALLOW_RE="${ERROR_ALLOW_RE:-}"
BATCHES="${BATCHES:-acc hr pay prod mkt svc sale sale_mi edi edi_inv l10n rem}"

BATCH_ACC="${BATCH_ACC:-account_accountant,account_reports,account_asset,account_asset_fleet,account_budget,project_account_budget,account_sepa,account_sepa_direct_debit,account_inter_company_rules,sale_purchase_inter_company_rules,account_followup,l10n_de_reports}"
BATCH_HR="${BATCH_HR:-hr_payroll,hr_payroll_account,hr_payroll_account_sepa,hr_appraisal,hr_appraisal_survey,hr_contract_salary,hr_referral,hr_recruitment_extract,planning,project_forecast}"
BATCH_PAY="${BATCH_PAY:-l10n_au_hr_payroll,l10n_au_hr_payroll_account,l10n_au_keypay,l10n_be_hr_payroll,l10n_ch_hr_payroll,l10n_ke_hr_payroll,l10n_lu_hr_payroll}"
BATCH_PROD="${BATCH_PROD:-documents,spreadsheet_edition,web_studio,whatsapp,voip,approvals,sign,iot,mrp_mps,mrp_workorder_iot,mrp_plm}"
BATCH_MKT="${BATCH_MKT:-social,social_facebook,social_instagram,social_linkedin,social_push_notifications,social_twitter}"
BATCH_SVC="${BATCH_SVC:-appointment,appointment_crm,frontdesk,helpdesk,helpdesk_sale_timesheet,industry_fsm_report,industry_fsm_sale_report,worksheet,sale_timesheet_enterprise}"
BATCH_SALE="${BATCH_SALE:-sale_subscription,sale_renting,sale_stock_renting,sale_renting_sign,website_sale_renting,website_sale_dashboard,website_delivery_sendcloud,website_sale_fedex,pos_pricer,pos_restaurant_appointment,pos_self_order_preparation_display,purchase_stock,spreadsheet_dashboard}"
BATCH_SALE_MI="${BATCH_SALE_MI:-website_delivery_sendcloud,website_sale_fedex}"
BATCH_EDI="${BATCH_EDI:-l10n_ar_edi,l10n_cl_edi,l10n_mx_edi,l10n_ec_edi,l10n_pe_edi,l10n_nl_reports_sbr,l10n_be_hr_payroll}"
BATCH_EDI_INV="${BATCH_EDI_INV:-l10n_ec_edi,l10n_pe_edi}"
BATCH_L10N="${BATCH_L10N:-l10n_mx_edi_stock,l10n_mx_edi_extended,l10n_br_avatax,l10n_br_edi,l10n_br_edi_sale,l10n_it_riba,l10n_be_codabox,l10n_in_reports_gstr}"
BATCH_REM="${BATCH_REM:-account_taxcloud,sale_account_taxcloud,sale_amazon_taxcloud,sale_loyalty_taxcloud,sale_loyalty_taxcloud_delivery,sale_subscription_taxcloud,website_sale_account_taxcloud,sale_ebay,l10n_account_customer_statements,l10n_uk_customer_statements,l10n_be_us_consolidation_demo,l10n_dk_edi,l10n_fr_reports_extended,mrp_subcontracting_studio,website_twitter_wall,website_event_twitter_wall}"

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
