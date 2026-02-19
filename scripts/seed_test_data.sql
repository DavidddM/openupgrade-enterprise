-- =============================================================================
-- OpenUpgrade Enterprise E2E Test: Seed Data for v17.0
-- =============================================================================
-- Seeds test data into a v17 database to exercise ALL 62 enterprise migration
-- scripts during the 17.0 -> 18.0 upgrade. Each section is wrapped in DO blocks
-- with IF EXISTS guards so it silently skips if the module wasn't installed.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. ACCOUNT_ACCOUNTANT: deferred journal/method renames + Kenya tax tags
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='deferred_journal_id') THEN
    INSERT INTO account_journal (name, code, type, company_id,
                                  invoice_reference_type, invoice_reference_model,
                                  debit_sepa_pain_version,
                                  create_uid, create_date, write_uid, write_date)
    SELECT '{"en_US": "Deferred Test Journal"}'::jsonb, 'DFRT', 'general', 1,
           'none', 'odoo',
           'pain.008.001.02',
           1, NOW(), 1, NOW()
    WHERE NOT EXISTS (SELECT 1 FROM account_journal WHERE code='DFRT' AND company_id=1);
    UPDATE res_company
    SET deferred_journal_id = (SELECT id FROM account_journal WHERE code='DFRT' AND company_id=1 LIMIT 1),
        deferred_amount_computation_method = 'day'
    WHERE id = 1 AND deferred_journal_id IS NULL;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 2. ACCOUNT_REPORTS: footnote -> annotation + opening_date_filter
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='account_report_footnote') THEN
    INSERT INTO account_report_footnote (report_id, text, create_uid, create_date, write_uid, write_date)
    SELECT (SELECT id FROM account_report LIMIT 1), 'Test footnote for migration', 1, NOW(), 1, NOW()
    WHERE EXISTS (SELECT 1 FROM account_report LIMIT 1)
    AND NOT EXISTS (SELECT 1 FROM account_report_footnote WHERE text='Test footnote for migration');
END IF;
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='account_report' AND column_name='default_opening_date_filter') THEN
    UPDATE account_report
    SET default_opening_date_filter = 'last_month'
    WHERE id = (SELECT id FROM account_report LIMIT 1)
    AND default_opening_date_filter IS NOT NULL;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 3. ACCOUNT_BUDGET: crossovered_budget states + rename
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='crossovered_budget') THEN
    INSERT INTO crossovered_budget (name, state, date_from, date_to, company_id, create_uid, create_date, write_uid, write_date)
    VALUES
        ('Budget Confirmed', 'confirm', '2024-01-01', '2024-12-31', 1, 1, NOW(), 1, NOW()),
        ('Budget Validated', 'validate', '2024-01-01', '2024-12-31', 1, 1, NOW(), 1, NOW()),
        ('Budget Cancelled', 'cancel', '2024-01-01', '2024-12-31', 1, 1, NOW(), 1, NOW())
    ON CONFLICT DO NOTHING;
    INSERT INTO crossovered_budget_lines (crossovered_budget_id, date_from, date_to, planned_amount, create_uid, create_date, write_uid, write_date)
    SELECT id, '2024-01-01', '2024-06-30', 5000.00, 1, NOW(), 1, NOW()
    FROM crossovered_budget WHERE name = 'Budget Confirmed'
    AND NOT EXISTS (SELECT 1 FROM crossovered_budget_lines WHERE planned_amount=5000);
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 4. ACCOUNT_ASSET: asset_model M2O -> M2M
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='account_account' AND column_name='asset_model') THEN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='account_asset') THEN
        INSERT INTO account_asset (name, state, method_number, method_period, acquisition_date,
                                    original_value, company_id, prorata_computation_type, prorata_date,
                                    create_uid, create_date, write_uid, write_date)
        SELECT 'Test Asset Model', 'model', 12, '1', '2024-01-01', 10000, 1, 'none', '2024-01-01',
               1, NOW(), 1, NOW()
        WHERE NOT EXISTS (SELECT 1 FROM account_asset WHERE name='Test Asset Model');
        UPDATE account_account
        SET asset_model = (SELECT id FROM account_asset WHERE name='Test Asset Model' LIMIT 1)
        WHERE id = (SELECT id FROM account_account WHERE company_id=1 LIMIT 1)
        AND asset_model IS NULL;
    END IF;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 5. ACCOUNT_ISO20022 (was account_sepa): field renames + pain version
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='sepa_orgid_id') THEN
    UPDATE res_company SET sepa_orgid_id = 'TESTORGID001' WHERE id = 1;
    UPDATE res_company SET sepa_orgid_issr = 'TestIssuer' WHERE id = 1;
END IF;
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='account_journal' AND column_name='sepa_pain_version') THEN
    UPDATE account_journal
    SET sepa_pain_version = 'pain.001.001.03.se'
    WHERE id = (SELECT id FROM account_journal WHERE company_id=1 AND type='bank' LIMIT 1)
    AND sepa_pain_version IS NULL;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 6. ACCOUNT_INTER_COMPANY_RULES: rule_type -> boolean
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='rule_type') THEN
    UPDATE res_company SET rule_type = 'invoice_and_refund' WHERE id = 1;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 7. SALE_PURCHASE_INTER_COMPANY_RULES: rule_type -> two booleans
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='rule_type') THEN
    IF (SELECT COUNT(*) FROM res_company) > 1 THEN
        UPDATE res_company SET rule_type = 'sale_purchase'
        WHERE id = (SELECT id FROM res_company WHERE id != 1 LIMIT 1);
    END IF;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 8. ACCOUNT_SEPA_DIRECT_DEBIT: sdd_mandate_id move->payment
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='sdd_mandate') THEN
    INSERT INTO sdd_mandate (name, state, partner_id, company_id, payment_journal_id,
                             sdd_scheme, start_date,
                             create_uid, create_date, write_uid, write_date)
    SELECT 'TEST-SDD-001', 'active',
           (SELECT id FROM res_partner WHERE company_id=1 LIMIT 1), 1,
           (SELECT id FROM account_journal WHERE company_id=1 AND type='bank' LIMIT 1),
           'CORE', NOW()::date,
           1, NOW(), 1, NOW()
    WHERE NOT EXISTS (SELECT 1 FROM sdd_mandate WHERE name='TEST-SDD-001');
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='account_move' AND column_name='sdd_mandate_id') THEN
        UPDATE account_move
        SET sdd_mandate_id = (SELECT id FROM sdd_mandate WHERE name='TEST-SDD-001' LIMIT 1)
        WHERE id = (SELECT am.id FROM account_move am
                    JOIN account_payment ap ON ap.move_id = am.id
                    LIMIT 1)
        AND sdd_mandate_id IS NULL;
    END IF;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 9. DOCUMENTS: folders, tags, type='empty'
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='documents_folder') THEN
    INSERT INTO documents_folder (name, company_id, create_uid, create_date, write_uid, write_date)
    SELECT '{"en_US": "Test Parent Folder"}'::jsonb, 1, 1, NOW(), 1, NOW()
    WHERE NOT EXISTS (SELECT 1 FROM documents_folder
                      WHERE name->>'en_US' = 'Test Parent Folder');
    INSERT INTO documents_folder (name, parent_folder_id, company_id,
                                   create_uid, create_date, write_uid, write_date)
    SELECT '{"en_US": "Test Child Folder"}'::jsonb,
           (SELECT id FROM documents_folder WHERE name->>'en_US' = 'Test Parent Folder' LIMIT 1),
           1, 1, NOW(), 1, NOW()
    WHERE NOT EXISTS (SELECT 1 FROM documents_folder
                      WHERE name->>'en_US' = 'Test Child Folder');
    INSERT INTO documents_document (name, folder_id, type, owner_id,
                                     create_uid, create_date, write_uid, write_date)
    SELECT 'Test Doc Binary',
           (SELECT id FROM documents_folder WHERE name->>'en_US' = 'Test Parent Folder' LIMIT 1),
           'binary', 1, 1, NOW(), 1, NOW()
    WHERE NOT EXISTS (SELECT 1 FROM documents_document WHERE name='Test Doc Binary');
    INSERT INTO documents_document (name, folder_id, type, owner_id,
                                     create_uid, create_date, write_uid, write_date)
    SELECT 'Test Doc Empty',
           (SELECT id FROM documents_folder WHERE name->>'en_US' = 'Test Parent Folder' LIMIT 1),
           'empty', 1, 1, NOW(), 1, NOW()
    WHERE NOT EXISTS (SELECT 1 FROM documents_document WHERE name='Test Doc Empty');
END IF;
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='documents_facet') THEN
    INSERT INTO documents_facet (name, create_uid, create_date, write_uid, write_date)
    SELECT '{"en_US": "Facet A"}'::jsonb, 1, NOW(), 1, NOW()
    WHERE NOT EXISTS (SELECT 1 FROM documents_facet WHERE name->>'en_US'='Facet A');
    INSERT INTO documents_facet (name, create_uid, create_date, write_uid, write_date)
    SELECT '{"en_US": "Facet B"}'::jsonb, 1, NOW(), 1, NOW()
    WHERE NOT EXISTS (SELECT 1 FROM documents_facet WHERE name->>'en_US'='Facet B');
    INSERT INTO documents_tag (name, facet_id, create_uid, create_date, write_uid, write_date)
    SELECT '{"en_US": "DupTag"}'::jsonb,
           (SELECT id FROM documents_facet WHERE name->>'en_US'='Facet A' LIMIT 1),
           1, NOW(), 1, NOW()
    WHERE NOT EXISTS (SELECT 1 FROM documents_tag
                      WHERE name->>'en_US'='DupTag'
                      AND facet_id=(SELECT id FROM documents_facet WHERE name->>'en_US'='Facet A' LIMIT 1));
    INSERT INTO documents_tag (name, facet_id, create_uid, create_date, write_uid, write_date)
    SELECT '{"en_US": "DupTag"}'::jsonb,
           (SELECT id FROM documents_facet WHERE name->>'en_US'='Facet B' LIMIT 1),
           1, NOW(), 1, NOW()
    WHERE NOT EXISTS (SELECT 1 FROM documents_tag
                      WHERE name->>'en_US'='DupTag'
                      AND facet_id=(SELECT id FROM documents_facet WHERE name->>'en_US'='Facet B' LIMIT 1));
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 10. SOCIAL: message + images for per-media split
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    v_media_id INTEGER;
    v_account_id INTEGER;
    v_utm_medium_id INTEGER;
    v_post_id INTEGER;
    v_attach_id INTEGER;
BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='social_post') THEN
    SELECT id INTO v_media_id FROM social_media LIMIT 1;
    IF v_media_id IS NOT NULL THEN
        SELECT id INTO v_utm_medium_id FROM utm_medium LIMIT 1;
        IF v_utm_medium_id IS NULL THEN
            INSERT INTO utm_medium (name, create_uid, create_date, write_uid, write_date)
            VALUES ('{"en_US": "Social Test"}'::jsonb, 1, NOW(), 1, NOW())
            RETURNING id INTO v_utm_medium_id;
        END IF;
        SELECT id INTO v_account_id FROM social_account LIMIT 1;
        IF v_account_id IS NULL THEN
            INSERT INTO social_account (name, media_id, utm_medium_id, create_uid, create_date, write_uid, write_date)
            VALUES ('Test Social Account', v_media_id, v_utm_medium_id, 1, NOW(), 1, NOW())
            RETURNING id INTO v_account_id;
        END IF;
        INSERT INTO ir_attachment (name, type, db_datas, res_model, create_uid, create_date, write_uid, write_date)
        SELECT 'social_test_image.png', 'binary',
               decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==', 'base64'),
               'social.post', 1, NOW(), 1, NOW()
        WHERE NOT EXISTS (SELECT 1 FROM ir_attachment WHERE name='social_test_image.png' AND res_model='social.post');
        SELECT id INTO v_attach_id FROM ir_attachment WHERE name='social_test_image.png' AND res_model='social.post' LIMIT 1;
        INSERT INTO social_post (message, state, post_method, youtube_video_privacy, source_id,
                                  create_uid, create_date, write_uid, write_date)
        SELECT 'Test social post message for migration', 'draft', 'now', 'public', v_account_id,
               1, NOW(), 1, NOW()
        WHERE NOT EXISTS (SELECT 1 FROM social_post WHERE message LIKE 'Test social post%')
        RETURNING id INTO v_post_id;
        IF v_post_id IS NULL THEN
            SELECT id INTO v_post_id FROM social_post WHERE message LIKE 'Test social post%' LIMIT 1;
        END IF;
        IF v_post_id IS NOT NULL AND v_attach_id IS NOT NULL THEN
            UPDATE ir_attachment SET res_id = v_post_id
            WHERE id = v_attach_id AND (res_id IS NULL OR res_id = 0);
        END IF;
    END IF;
END IF;
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='social_post_template') THEN
    INSERT INTO social_post_template (message, create_uid, create_date, write_uid, write_date)
    SELECT 'Test template message for migration', 1, NOW(), 1, NOW()
    WHERE NOT EXISTS (SELECT 1 FROM social_post_template WHERE message LIKE 'Test template%');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 11. SPREADSHEET_EDITION: revision_id -> revision_uuid, parent Char -> M2O
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='spreadsheet_revision') THEN
    DECLARE
        v_res_model TEXT := 'spreadsheet.dashboard';
        v_res_id INTEGER;
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='spreadsheet_dashboard') THEN
            SELECT id INTO v_res_id FROM spreadsheet_dashboard LIMIT 1;
        END IF;
        IF v_res_id IS NULL THEN
            v_res_model := 'documents.document';
            SELECT id INTO v_res_id FROM documents_document WHERE type='spreadsheet' LIMIT 1;
        END IF;
        IF v_res_id IS NOT NULL THEN
            INSERT INTO spreadsheet_revision (revision_id, parent_revision_id, res_model, res_id,
                                              commands, create_uid, create_date, write_uid, write_date)
            SELECT 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', '', v_res_model, v_res_id,
                   '{}', 1, NOW(), 1, NOW()
            WHERE NOT EXISTS (SELECT 1 FROM spreadsheet_revision
                              WHERE revision_id='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee');
            INSERT INTO spreadsheet_revision (revision_id, parent_revision_id, res_model, res_id,
                                              commands, create_uid, create_date, write_uid, write_date)
            SELECT 'ffffffff-1111-2222-3333-444444444444',
                   'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', v_res_model, v_res_id,
                   '{"type":"SET"}', 1, NOW(), 1, NOW()
            WHERE NOT EXISTS (SELECT 1 FROM spreadsheet_revision
                              WHERE revision_id='ffffffff-1111-2222-3333-444444444444');
        END IF;
    END;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 12. VOIP: ir.config_parameter -> voip.provider
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM ir_module_module WHERE name='voip' AND state='installed') THEN
    INSERT INTO ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date)
    VALUES ('voip.wsServer', 'wss://voip.example.com', 1, NOW(), 1, NOW())
    ON CONFLICT (key) DO UPDATE SET value = 'wss://voip.example.com';
    INSERT INTO ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date)
    VALUES ('voip.pbx_ip', 'pbx.example.com', 1, NOW(), 1, NOW())
    ON CONFLICT (key) DO UPDATE SET value = 'pbx.example.com';
    INSERT INTO ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date)
    VALUES ('voip.mode', 'prod', 1, NOW(), 1, NOW())
    ON CONFLICT (key) DO UPDATE SET value = 'prod';
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 13. PLANNING: bool->selection + duration hours->days
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='planning_allow_self_unassign') THEN
    UPDATE res_company SET planning_allow_self_unassign = true WHERE id = 1;
END IF;
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='planning_slot_template') THEN
    INSERT INTO planning_slot_template (duration,
                                         create_uid, create_date, write_uid, write_date)
    SELECT 24.0, 1, NOW(), 1, NOW()
    WHERE NOT EXISTS (SELECT 1 FROM planning_slot_template WHERE duration=24.0);
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 14. PROJECT_FORECAST: ir_property -> M2O project_id
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='planning_slot_template') THEN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='project_project') THEN
        DECLARE
            v_template_id INTEGER;
            v_project_id INTEGER;
            v_field_id INTEGER;
        BEGIN
            SELECT id INTO v_template_id FROM planning_slot_template LIMIT 1;
            SELECT id INTO v_project_id FROM project_project WHERE company_id=1 LIMIT 1;
            SELECT id INTO v_field_id FROM ir_model_fields
            WHERE model='planning.slot.template' AND name='project_id' LIMIT 1;
            IF v_template_id IS NOT NULL AND v_project_id IS NOT NULL AND v_field_id IS NOT NULL THEN
                INSERT INTO ir_property (name, fields_id, type, res_id, value_reference, company_id,
                                          create_uid, create_date, write_uid, write_date)
                SELECT 'project_id', v_field_id, 'many2one',
                       'planning.slot.template,' || v_template_id,
                       'project.project,' || v_project_id, 1,
                       1, NOW(), 1, NOW()
                WHERE NOT EXISTS (
                    SELECT 1 FROM ir_property
                    WHERE fields_id = v_field_id
                    AND res_id = 'planning.slot.template,' || v_template_id
                );
            END IF;
        END;
    END IF;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 15. MRP_MPS: manufacturing_period split
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='manufacturing_period') THEN
    UPDATE res_company SET manufacturing_period = 'month' WHERE id = 1;
END IF;
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='manufacturing_period_to_display') THEN
    UPDATE res_company SET manufacturing_period_to_display = 6 WHERE id = 1;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 16. WORKSHEET: M2M company_ids -> M2O company_id
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='worksheet_template') THEN
    INSERT INTO worksheet_template (name, create_uid, create_date, write_uid, write_date)
    SELECT 'Test Worksheet Template', 1, NOW(), 1, NOW()
    WHERE NOT EXISTS (SELECT 1 FROM worksheet_template WHERE name='Test Worksheet Template');
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='worksheet_template_res_company_rel') THEN
        INSERT INTO worksheet_template_res_company_rel (worksheet_template_id, res_company_id)
        SELECT (SELECT id FROM worksheet_template WHERE name='Test Worksheet Template' LIMIT 1), 1
        WHERE NOT EXISTS (
            SELECT 1 FROM worksheet_template_res_company_rel
            WHERE worksheet_template_id = (SELECT id FROM worksheet_template WHERE name='Test Worksheet Template' LIMIT 1)
        );
    END IF;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 17. FRONTDESK: populate visitor company_id from station
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='frontdesk_visitor') THEN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='frontdesk_frontdesk') THEN
        INSERT INTO frontdesk_frontdesk (name, company_id, ask_phone, ask_email, ask_company,
                                         access_token,
                                         create_uid, create_date, write_uid, write_date)
        SELECT 'Test Station', 1, false, false, false,
               'test-access-token-12345',
               1, NOW(), 1, NOW()
        WHERE NOT EXISTS (SELECT 1 FROM frontdesk_frontdesk WHERE name='Test Station');
        INSERT INTO frontdesk_visitor (name, station_id, create_uid, create_date, write_uid, write_date)
        SELECT 'Test Visitor',
               (SELECT id FROM frontdesk_frontdesk WHERE name='Test Station' LIMIT 1),
               1, NOW(), 1, NOW()
        WHERE NOT EXISTS (SELECT 1 FROM frontdesk_visitor WHERE name='Test Visitor');
    END IF;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 18. WHATSAPP: whatsapp_mail_message_id -> last_wa_mail_message_id
-- ---------------------------------------------------------------------------
-- Field rename only, no seed data needed beyond having the column exist

-- ---------------------------------------------------------------------------
-- 19. WEB_STUDIO: group_id -> approval_group_id
-- ---------------------------------------------------------------------------
-- Field rename only, no special seed data needed

-- ---------------------------------------------------------------------------
-- 20. APPOINTMENT: resource_manual_confirmation rename
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='appointment_type' AND column_name='resource_manual_confirmation') THEN
    UPDATE appointment_type SET resource_manual_confirmation = true
    WHERE id = (SELECT id FROM appointment_type LIMIT 1);
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 21. HR_PAYROLL: deduction_type_id -> other_input_type_id
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='hr_salary_attachment_type') THEN
    INSERT INTO hr_salary_attachment_type (name, code, create_uid, create_date, write_uid, write_date)
    SELECT '{"en_US": "Custom Deduction"}'::jsonb, 'CUSTOM_DED', 1, NOW(), 1, NOW()
    WHERE NOT EXISTS (SELECT 1 FROM hr_salary_attachment_type WHERE code='CUSTOM_DED');
END IF;
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='hr_salary_attachment') THEN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='hr_salary_attachment' AND column_name='deduction_type_id') THEN
        INSERT INTO hr_salary_attachment (deduction_type_id, description, monthly_amount, total_amount,
                                           company_id, state, date_start,
                                           create_uid, create_date, write_uid, write_date)
        SELECT (SELECT id FROM hr_salary_attachment_type WHERE code='CUSTOM_DED' LIMIT 1),
               'Test attachment', 100.00, 1200.00,
               1, 'open', '2024-01-01',
               1, NOW(), 1, NOW()
        WHERE EXISTS (SELECT 1 FROM hr_salary_attachment_type WHERE code='CUSTOM_DED')
        AND NOT EXISTS (SELECT 1 FROM hr_salary_attachment WHERE description='Test attachment');
    END IF;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 22. HR_APPRAISAL: feedback templates -> hr.appraisal.template
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='appraisal_employee_feedback_template') THEN
    UPDATE res_company
    SET appraisal_employee_feedback_template = '"<p>Employee feedback template for migration test</p>"'::jsonb,
        appraisal_manager_feedback_template = '"<p>Manager feedback template for migration test</p>"'::jsonb
    WHERE id = 1;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 23. HR_CONTRACT_SALARY: hide_description inversion + color remap
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='hr_contract_salary_benefit') THEN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='hr_contract_salary_benefit' AND column_name='hide_description') THEN
        INSERT INTO hr_contract_salary_benefit (name, hide_description,
                                                 res_field_id, structure_type_id,
                                                 benefit_type_id,
                                                 create_uid, create_date, write_uid, write_date)
        SELECT '{"en_US": "Test Benefit"}'::jsonb, true,
               (SELECT id FROM ir_model_fields WHERE model='hr.contract' AND name='wage' LIMIT 1),
               (SELECT id FROM hr_payroll_structure_type LIMIT 1),
               (SELECT id FROM hr_contract_salary_benefit_type LIMIT 1),
               1, NOW(), 1, NOW()
        WHERE NOT EXISTS (SELECT 1 FROM hr_contract_salary_benefit WHERE name->>'en_US'='Test Benefit');
    END IF;
END IF;
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='hr_contract_salary_benefit_value') THEN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='hr_contract_salary_benefit_value' AND column_name='color') THEN
        INSERT INTO hr_contract_salary_benefit_value (
            benefit_id, value, color, hide_description, name,
            create_uid, create_date, write_uid, write_date)
        SELECT (SELECT id FROM hr_contract_salary_benefit WHERE name->>'en_US'='Test Benefit' LIMIT 1),
               100.0, 'red', false, '{"en_US": "Option A"}'::jsonb,
               1, NOW(), 1, NOW()
        WHERE EXISTS (SELECT 1 FROM hr_contract_salary_benefit WHERE name->>'en_US'='Test Benefit')
        AND NOT EXISTS (SELECT 1 FROM hr_contract_salary_benefit_value WHERE value=100.0
                        AND benefit_id=(SELECT id FROM hr_contract_salary_benefit WHERE name->>'en_US'='Test Benefit' LIMIT 1));
    END IF;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 24. SALE_TIMESHEET_ENTERPRISE: implied_group -> company boolean
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM ir_model_data
           WHERE module='sale_timesheet_enterprise'
           AND name='group_use_timesheet_leaderboard') THEN
    INSERT INTO res_groups_implied_rel (gid, hid)
    SELECT
        (SELECT res_id FROM ir_model_data WHERE module='base' AND name='group_user'),
        (SELECT res_id FROM ir_model_data WHERE module='sale_timesheet_enterprise' AND name='group_use_timesheet_leaderboard')
    WHERE NOT EXISTS (
        SELECT 1 FROM res_groups_implied_rel
        WHERE gid = (SELECT res_id FROM ir_model_data WHERE module='base' AND name='group_user')
        AND hid = (SELECT res_id FROM ir_model_data WHERE module='sale_timesheet_enterprise' AND name='group_use_timesheet_leaderboard')
    );
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 25. L10N_AR_EDI: Binary certificate fields
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='l10n_ar_afip_ws_key') THEN
    UPDATE res_company
    SET l10n_ar_afip_ws_key = decode('LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0t', 'base64'),
        l10n_ar_afip_ws_crt = decode('LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0t', 'base64'),
        l10n_ar_afip_ws_crt_fname = 'ar_test_cert.pem'
    WHERE id = (SELECT rc.id FROM res_company rc
                JOIN res_partner rp ON rp.id = rc.partner_id
                JOIN res_country c ON c.id = rp.country_id
                WHERE c.code = 'AR' LIMIT 1)
    AND l10n_ar_afip_ws_key IS NULL;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 26. L10N_CL_EDI: l10n_cl_certificate -> certificate.certificate
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='l10n_cl_certificate') THEN
    INSERT INTO l10n_cl_certificate (certificate, private_key, signature_pass_phrase,
                                      signature_filename, company_id,
                                      create_uid, create_date, write_uid, write_date)
    SELECT decode('LS0tLS1CRUdJTiBQS0NTMTIt', 'base64'),
           decode('LS0tLS1CRUdJTiBLRVkt', 'base64'), 'testpass',
           'cl_cert.pfx',
           (SELECT rc.id FROM res_company rc
            JOIN res_partner rp ON rp.id = rc.partner_id
            JOIN res_country c ON c.id = rp.country_id
            WHERE c.code = 'CL' LIMIT 1),
           1, NOW(), 1, NOW()
    WHERE EXISTS (SELECT 1 FROM res_company rc
                  JOIN res_partner rp ON rp.id = rc.partner_id
                  JOIN res_country c ON c.id = rp.country_id
                  WHERE c.code = 'CL')
    AND NOT EXISTS (SELECT 1 FROM l10n_cl_certificate WHERE signature_filename='cl_cert.pfx');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 27. L10N_EC_EDI: l10n_ec_edi_certificate -> certificate.certificate
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='l10n_ec_edi_certificate') THEN
    INSERT INTO l10n_ec_edi_certificate (password, file_name, company_id,
                                          create_uid, create_date, write_uid, write_date)
    SELECT 'ecpass', 'ec_cert.pfx',
           (SELECT rc.id FROM res_company rc
            JOIN res_partner rp ON rp.id = rc.partner_id
            JOIN res_country c ON c.id = rp.country_id
            WHERE c.code = 'EC' LIMIT 1),
           1, NOW(), 1, NOW()
    WHERE EXISTS (SELECT 1 FROM res_company rc
                  JOIN res_partner rp ON rp.id = rc.partner_id
                  JOIN res_country c ON c.id = rp.country_id
                  WHERE c.code = 'EC')
    AND NOT EXISTS (SELECT 1 FROM l10n_ec_edi_certificate WHERE file_name='ec_cert.pfx');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 28. L10N_MX_EDI: cert+key+addenda
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='l10n_mx_edi_certificate') THEN
    INSERT INTO l10n_mx_edi_certificate (content, key, password, serial_number, company_id,
                                          create_uid, create_date, write_uid, write_date)
    SELECT decode('LS0tLS1CRUdJTiBDRVJU', 'base64'),
           decode('LS0tLS1CRUdJTiBLRVkt', 'base64'),
           'mxpass', 'MX000001',
           (SELECT rc.id FROM res_company rc
            JOIN res_partner rp ON rp.id = rc.partner_id
            JOIN res_country c ON c.id = rp.country_id
            WHERE c.code = 'MX' LIMIT 1),
           1, NOW(), 1, NOW()
    WHERE EXISTS (SELECT 1 FROM res_company rc
                  JOIN res_partner rp ON rp.id = rc.partner_id
                  JOIN res_country c ON c.id = rp.country_id
                  WHERE c.code = 'MX')
    AND NOT EXISTS (SELECT 1 FROM l10n_mx_edi_certificate WHERE serial_number='MX000001');
END IF;
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='ir_ui_view' AND column_name='l10n_mx_edi_addenda_flag') THEN
    INSERT INTO ir_ui_view (name, type, arch_db, l10n_mx_edi_addenda_flag,
                             priority, mode, key,
                             create_uid, create_date, write_uid, write_date)
    SELECT 'Test MX Addenda', 'qweb',
           '"<t t-name=\"test_addenda\"><addenda>Test</addenda></t>"'::jsonb, true,
           16, 'primary', 'test_mx_addenda_view',
           1, NOW(), 1, NOW()
    WHERE NOT EXISTS (SELECT 1 FROM ir_ui_view WHERE name='Test MX Addenda');
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='res_partner' AND column_name='l10n_mx_edi_addenda') THEN
        UPDATE res_partner
        SET l10n_mx_edi_addenda = (SELECT id FROM ir_ui_view WHERE name='Test MX Addenda' LIMIT 1)
        WHERE id = (SELECT rp.id FROM res_partner rp
                    JOIN res_country c ON c.id = rp.country_id
                    WHERE c.code = 'MX' LIMIT 1)
        AND l10n_mx_edi_addenda IS NULL;
    END IF;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 29. L10N_PE_EDI: l10n_pe_edi_certificate -> certificate.certificate
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='l10n_pe_edi_certificate') THEN
    INSERT INTO l10n_pe_edi_certificate (password, serial_number, company_id,
                                          create_uid, create_date, write_uid, write_date)
    SELECT 'pepass', 'PE000001',
           (SELECT rc.id FROM res_company rc
            JOIN res_partner rp ON rp.id = rc.partner_id
            JOIN res_country c ON c.id = rp.country_id
            WHERE c.code = 'PE' LIMIT 1),
           1, NOW(), 1, NOW()
    WHERE EXISTS (SELECT 1 FROM res_company rc
                  JOIN res_partner rp ON rp.id = rc.partner_id
                  JOIN res_country c ON c.id = rp.country_id
                  WHERE c.code = 'PE')
    AND NOT EXISTS (SELECT 1 FROM l10n_pe_edi_certificate WHERE serial_number='PE000001');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 30. L10N_NL_REPORTS_SBR: Binary cert fields -> certificate records
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='l10n_nl_reports_sbr_cert') THEN
    UPDATE res_company
    SET l10n_nl_reports_sbr_cert = decode('LS0tLS1CRUdJTiBDRVJU', 'base64'),
        l10n_nl_reports_sbr_key = decode('LS0tLS1CRUdJTiBLRVkt', 'base64'),
        l10n_nl_reports_sbr_server_root_cert = decode('LS0tLS1CRUdJTiBDQSBDRVJU', 'base64'),
        l10n_nl_reports_sbr_cert_filename = 'nl_sbr_cert.pem',
        l10n_nl_reports_sbr_key_filename = 'nl_sbr_key.pem'
    WHERE id = (SELECT rc.id FROM res_company rc
                JOIN res_partner rp ON rp.id = rc.partner_id
                JOIN res_country c ON c.id = rp.country_id
                WHERE c.code = 'NL' LIMIT 1)
    AND l10n_nl_reports_sbr_cert IS NULL;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 31. L10N_DE_REPORTS: DATEV identifier company-dependent conversion
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_partner' AND column_name='l10n_de_datev_identifier') THEN
    UPDATE res_partner SET l10n_de_datev_identifier = 10001
    WHERE id = (SELECT id FROM res_partner WHERE company_id = 1 AND is_company = false LIMIT 1)
    AND l10n_de_datev_identifier IS NULL;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 32. L10N_BE_CODABOX: clean is_connected when no token
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='l10n_be_codabox_is_connected') THEN
    UPDATE res_company
    SET l10n_be_codabox_is_connected = true,
        l10n_be_codabox_iap_token = NULL
    WHERE id = (SELECT rc.id FROM res_company rc
                JOIN res_partner rp ON rp.id = rc.partner_id
                JOIN res_country c ON c.id = rp.country_id
                WHERE c.code = 'BE' LIMIT 1);
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 33. L10N_AU_HR_PAYROLL: casual_loading + withholding + employment_basis
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='hr_contract' AND column_name='l10n_au_casual_loading') THEN
    UPDATE hr_contract
    SET l10n_au_casual_loading = 25.0,
        l10n_au_withholding_variation = true,
        l10n_au_withholding_variation_amount = 15.5
    WHERE id = (SELECT id FROM hr_contract WHERE state='open' LIMIT 1)
    AND l10n_au_casual_loading IS NULL;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 34. L10N_BE_HR_PAYROLL: fiscal_voluntary_rate contract -> employee
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='hr_contract' AND column_name='fiscal_voluntary_rate') THEN
    UPDATE hr_contract
    SET fiscal_voluntary_rate = 33.50
    WHERE id = (SELECT id FROM hr_contract WHERE state='open' LIMIT 1)
    AND fiscal_voluntary_rate IS NULL;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 35. L10N_CH_HR_PAYROLL: insurance_code from insurance_company
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='l10n_ch_social_insurance') THEN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='l10n_ch_social_insurance' AND column_name='insurance_company') THEN
        INSERT INTO l10n_ch_social_insurance (name, insurance_company, insurance_code,
                                               age_start, age_stop_male, age_stop_female,
                                               company_id,
                                               create_uid, create_date, write_uid, write_date)
        SELECT 'Test AVS/AI/APG', 'Compenswiss', '',
               18, 65, 64,
               1,
               1, NOW(), 1, NOW()
        WHERE NOT EXISTS (SELECT 1 FROM l10n_ch_social_insurance WHERE insurance_company='Compenswiss');
    END IF;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 36. L10N_KE_HR_PAYROLL: l10n_ke_disabled -> disabled
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='hr_employee' AND column_name='l10n_ke_disabled') THEN
    UPDATE hr_employee SET l10n_ke_disabled = true
    WHERE id = (SELECT id FROM hr_employee LIMIT 1)
    AND (l10n_ke_disabled IS NULL OR l10n_ke_disabled = false);
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 37. IOT: iot_channel table (will be dropped)
-- ---------------------------------------------------------------------------
-- The iot_channel table exists if iot module was installed; nothing to seed.
-- The migration drops it. We just verify it's gone after.

-- ---------------------------------------------------------------------------
-- Done! Summary of seeded data:
-- - Accounting: deferred journal, footnote, budget states, asset model, SEPA/ISO20022, inter-company rules, SDD mandate
-- - Certificates: AR, CL, EC, MX (cert+key+addenda), PE, NL (cert+key+root)
-- - Documents: folders, documents, duplicate tags
-- - HR: salary attachment types, appraisal templates, contract salary benefits, AU/BE/CH/KE payroll
-- - Social: posts with messages and images
-- - Spreadsheet: revisions with parent chain
-- - Other: VoIP config, planning templates, worksheet templates, frontdesk visitors, MRP MPS periods
-- ---------------------------------------------------------------------------
