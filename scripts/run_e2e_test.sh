#!/bin/bash
# =============================================================================
# OpenUpgrade Enterprise E2E Test Orchestrator
# =============================================================================
# Tests ALL 62 enterprise migration scripts by:
#   Phase 1: Creating a v17 database with all modules installed
#   Phase 2: Seeding test data that exercises every migration script
#   Phase 3: Running the 17.0 -> 18.0 upgrade
#   Phase 4: Verifying migration results with 50+ SQL checks
# =============================================================================

set -euo pipefail

DB_NAME="${DB_NAME:-test_e2e_v17}"
DB_BACKUP="${DB_NAME}_backup"
DB_HOST="${DB_HOST:-db}"
DB_USER="${DB_USER:-odoo}"
DB_PASSWORD="${DB_PASSWORD:-odoo}"
ODOO_DIR="${ODOO_DIR:-/workspace/odoo}"
ENTERPRISE_DIR="${ENTERPRISE_DIR:-/workspace/enterprise}"
OPENUPGRADE_DIR="${OPENUPGRADE_DIR:-/workspace/odoo/openupgrade18}"
OUE_DIR="${OUE_DIR:-/workspace/odoo/openupgrade-enterprise}"
SCRIPTS_DIR="${OUE_DIR}/scripts"
LOG_DIR="/tmp"
VENV="${VENV:-/home/claude/odoo-venv/bin/activate}"

ODOO_COMMON="--db_host=${DB_HOST} --db_user=${DB_USER} --db_password=${DB_PASSWORD} --stop-after-init --no-http"
ADDONS_PATH_V17="${ODOO_DIR}/addons,${ENTERPRISE_DIR}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date +%H:%M:%S)] WARNING:${NC} $1"; }
err() { echo -e "${RED}[$(date +%H:%M:%S)] ERROR:${NC} $1"; }

psql_cmd() {
    PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -U "${DB_USER}" -d "$1" -q "$2"
}

# =============================================================================
# Phase 0: Setup
# =============================================================================
phase0_setup() {
    log "Phase 0: Setup and branch verification"

    source "${VENV}"

    cd "${ODOO_DIR}"
    ODOO_BRANCH=$(git branch --show-current)
    if [ "${ODOO_BRANCH}" != "17.0" ]; then
        log "Switching Odoo to 17.0 (currently on ${ODOO_BRANCH})"
        git checkout 17.0
    fi
    log "Odoo branch: $(git branch --show-current)"

    cd "${ENTERPRISE_DIR}"
    ENT_BRANCH=$(git branch --show-current)
    if [ "${ENT_BRANCH}" != "17.0" ]; then
        log "Switching Enterprise to 17.0 (currently on ${ENT_BRANCH})"
        git checkout 17.0
    fi
    log "Enterprise branch: $(git branch --show-current)"

    cd "${OUE_DIR}"
}

# =============================================================================
# Phase 1: Create v17 Database & Install Modules
# =============================================================================
phase1_install() {
    log "Phase 1: Creating v17 database and installing modules"

    PGPASSWORD="${DB_PASSWORD}" dropdb -h "${DB_HOST}" -U "${DB_USER}" --if-exists "${DB_NAME}" 2>/dev/null || true
    PGPASSWORD="${DB_PASSWORD}" dropdb -h "${DB_HOST}" -U "${DB_USER}" --if-exists "${DB_BACKUP}" 2>/dev/null || true

    PGPASSWORD="${DB_PASSWORD}" createdb -h "${DB_HOST}" -U "${DB_USER}" "${DB_NAME}"
    log "Created database: ${DB_NAME}"

    log "Installing base..."
    "${ODOO_DIR}/odoo-bin" -d "${DB_NAME}" \
        --addons-path="${ADDONS_PATH_V17}" \
        -i base --without-demo=all ${ODOO_COMMON} \
        --log-level=warn \
        2>&1 | tail -5

    log "Creating multi-company structure..."
    PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -U "${DB_USER}" -d "${DB_NAME}" -q <<'EOSQL'
DO $$ DECLARE
    v_country_id INTEGER;
    v_partner_id INTEGER;
    v_company_id INTEGER;
    v_currency_id INTEGER;
    v_countries TEXT[] := ARRAY['AR','CL','EC','MX','PE','NL','DE','BE','CH','AU','KE'];
    v_code TEXT;
BEGIN
    SELECT currency_id INTO v_currency_id FROM res_company WHERE id = 1;
    FOREACH v_code IN ARRAY v_countries LOOP
        SELECT id INTO v_country_id FROM res_country WHERE code = v_code;
        IF v_country_id IS NOT NULL THEN
            INSERT INTO res_partner (name, is_company, country_id, company_id,
                                     create_uid, create_date, write_uid, write_date)
            VALUES ('Company ' || v_code, true, v_country_id, NULL,
                    1, NOW(), 1, NOW())
            RETURNING id INTO v_partner_id;
            INSERT INTO res_company (name, partner_id, parent_id, currency_id,
                                      layout_background,
                                      create_uid, create_date, write_uid, write_date)
            VALUES ('Company ' || v_code, v_partner_id, 1, v_currency_id,
                    'Blank',
                    1, NOW(), 1, NOW())
            RETURNING id INTO v_company_id;
            UPDATE res_partner
            SET company_id = v_company_id,
                country_id = v_country_id
            WHERE id = v_partner_id;
            RAISE NOTICE 'Created company for %: id=%', v_code, v_company_id;
        END IF;
    END LOOP;
END $$;
EOSQL

    local batches=(
        "account_accountant,account_reports,account_asset,account_budget,account_sepa,account_sepa_direct_debit,account_inter_company_rules,sale_purchase_inter_company_rules"
        "hr_payroll,hr_appraisal,hr_appraisal_survey,hr_contract_salary,hr_referral,planning,project_forecast"
        "documents,social,social_facebook,social_instagram,social_linkedin,social_push_notifications,social_twitter,mrp_mps,mrp_plm"
        "sale_timesheet_enterprise,sale_subscription,sale_renting,sale_stock_renting,helpdesk,helpdesk_sale_timesheet,website_sale_renting,website_sale_dashboard"
        "spreadsheet_edition,appointment,appointment_crm,approvals,voip,whatsapp,web_studio,worksheet,frontdesk,iot,industry_fsm_report,project_account_budget"
        "l10n_de_reports,l10n_be_codabox,l10n_ar_edi,l10n_cl_edi,l10n_ec_edi,l10n_mx_edi,l10n_pe_edi,l10n_nl_reports_sbr"
        "l10n_au_hr_payroll,l10n_be_hr_payroll,l10n_ch_hr_payroll,l10n_ke_hr_payroll"
        "website_delivery_sendcloud,website_sale_fedex,account_asset_fleet"
    )

    local batch_num=1
    for batch in "${batches[@]}"; do
        log "Installing batch ${batch_num}/8: ${batch}"
        if "${ODOO_DIR}/odoo-bin" -d "${DB_NAME}" \
            --addons-path="${ADDONS_PATH_V17}" \
            -i "${batch}" --without-demo=all ${ODOO_COMMON} \
            --log-level=warn \
            --logfile="${LOG_DIR}/install_batch${batch_num}.log" \
            2>&1 | tail -3; then
            log "Batch ${batch_num} installed successfully"
        else
            warn "Batch ${batch_num} had issues (exit code $?). Check ${LOG_DIR}/install_batch${batch_num}.log"
            if grep -q "ERROR" "${LOG_DIR}/install_batch${batch_num}.log" 2>/dev/null; then
                grep "ERROR" "${LOG_DIR}/install_batch${batch_num}.log" | head -5
            fi
        fi
        batch_num=$((batch_num + 1))
    done

    log "Phase 1 complete. Checking installed modules..."
    PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -U "${DB_USER}" -d "${DB_NAME}" -t -c \
        "SELECT COUNT(*) || ' modules installed' FROM ir_module_module WHERE state='installed'"
}

# =============================================================================
# Phase 2: Seed Test Data
# =============================================================================
phase2_seed() {
    log "Phase 2: Seeding test data"

    PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -U "${DB_USER}" -d "${DB_NAME}" \
        -f "${SCRIPTS_DIR}/seed_test_data.sql" \
        2>&1 | grep -v "^$" | tail -20

    log "Phase 2 complete. Test data seeded."
}

# =============================================================================
# Phase 3: Run the Upgrade
# =============================================================================
phase3_upgrade() {
    log "Phase 3: Running the upgrade"

    log "Creating backup: ${DB_BACKUP}"
    PGPASSWORD="${DB_PASSWORD}" createdb -h "${DB_HOST}" -U "${DB_USER}" "${DB_BACKUP}" \
        -T "${DB_NAME}" 2>/dev/null || warn "Backup creation failed (concurrent access?)"

    log "Switching Odoo to 18.0..."
    cd "${ODOO_DIR}" && git checkout 18.0
    log "Switching Enterprise to 18.0..."
    cd "${ENTERPRISE_DIR}" && git checkout 18.0
    cd "${OUE_DIR}"

    local ADDONS_PATH_V18="${ODOO_DIR}/addons,${ENTERPRISE_DIR},${OPENUPGRADE_DIR}"

    local UPGRADE_PATH="${OPENUPGRADE_DIR}/openupgrade_scripts/scripts"
    UPGRADE_PATH="${UPGRADE_PATH},${OUE_DIR}/openupgrade_scripts_ee"

    log "Starting upgrade... (this may take 30-45 minutes)"
    log "Addons path: ${ADDONS_PATH_V18}"
    log "Upgrade path: ${UPGRADE_PATH}"
    log "Log file: ${LOG_DIR}/upgrade_e2e.log"

    local UPGRADE_EXIT=0
    "${ODOO_DIR}/odoo-bin" -d "${DB_NAME}" \
        --addons-path="${ADDONS_PATH_V18}" \
        --upgrade-path="${UPGRADE_PATH}" \
        --load=web,openupgrade_framework \
        -u all ${ODOO_COMMON} \
        --log-level=info \
        --logfile="${LOG_DIR}/upgrade_e2e.log" \
        2>&1 | tee "${LOG_DIR}/upgrade_e2e_console.log" | tail -20 \
        || UPGRADE_EXIT=$?

    log "Upgrade exit code: ${UPGRADE_EXIT}"

    local ERROR_COUNT=0
    if [ -f "${LOG_DIR}/upgrade_e2e.log" ]; then
        ERROR_COUNT=$(grep -c "ERROR" "${LOG_DIR}/upgrade_e2e.log" 2>/dev/null || echo "0")
        log "Total ERROR lines in log: ${ERROR_COUNT}"
        if [ "${ERROR_COUNT}" -gt 0 ]; then
            warn "First 10 errors:"
            grep "ERROR" "${LOG_DIR}/upgrade_e2e.log" | head -10
        fi
    fi

    if [ "${UPGRADE_EXIT}" -ne 0 ]; then
        err "Upgrade failed with exit code ${UPGRADE_EXIT}"
        err "Check ${LOG_DIR}/upgrade_e2e.log for details"
        return 1
    fi

    log "Phase 3 complete. Upgrade finished."
}

# =============================================================================
# Phase 4: Verification
# =============================================================================
phase4_verify() {
    log "Phase 4: Running verification queries"

    PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -U "${DB_USER}" -d "${DB_NAME}" \
        -f "${SCRIPTS_DIR}/verify_migration.sql" \
        2>&1

    log "Phase 4 complete."
}

# =============================================================================
# Cleanup: Switch enterprise back to 17.0
# =============================================================================
cleanup() {
    log "Cleanup: Switching Enterprise back to 17.0"
    cd "${ENTERPRISE_DIR}" && git checkout 17.0 2>/dev/null || true
    cd "${ODOO_DIR}" && git checkout 17.0 2>/dev/null || true
    cd "${OUE_DIR}"
}

# =============================================================================
# Main
# =============================================================================
main() {
    local START_TIME=$(date +%s)

    log "=========================================="
    log "OpenUpgrade Enterprise E2E Test"
    log "=========================================="
    log "Database: ${DB_NAME}"
    log "Odoo: ${ODOO_DIR}"
    log "Enterprise: ${ENTERPRISE_DIR}"
    log "OpenUpgrade: ${OPENUPGRADE_DIR}"
    log "=========================================="

    local PHASE="${1:-all}"

    case "${PHASE}" in
        setup|0)   phase0_setup ;;
        install|1) phase0_setup; phase1_install ;;
        seed|2)    phase2_seed ;;
        upgrade|3) phase3_upgrade ;;
        verify|4)  phase4_verify ;;
        all)
            phase0_setup
            phase1_install
            phase2_seed
            phase3_upgrade
            phase4_verify
            cleanup
            ;;
        *)
            echo "Usage: $0 [setup|install|seed|upgrade|verify|all]"
            exit 1
            ;;
    esac

    local END_TIME=$(date +%s)
    local ELAPSED=$(( (END_TIME - START_TIME) / 60 ))
    log "=========================================="
    log "Total time: ${ELAPSED} minutes"
    log "=========================================="
}

trap cleanup EXIT

main "$@"
