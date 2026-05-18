# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    """Carry the CV digitization state of applicants over to their candidates.

    18.0 moves the extract fields from hr.applicant to the new hr.candidate,
    which the OpenUpgrade hr_recruitment migration creates from the applicants
    before this module loads. A candidate still in its default state takes the
    request state, status and IAP document id of its latest applicant that
    sent a CV, so a pending extraction is still fetched and a done one is not
    sent and paid for again. A second run changes nothing.
    """
    if not openupgrade.column_exists(env.cr, "hr_applicant", "extract_state"):
        return
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE hr_candidate candidate
        SET extract_state = applicant.extract_state,
            extract_status = applicant.extract_status,
            extract_document_uuid = applicant.extract_document_uuid,
            extract_state_processed = applicant.extract_state = 'waiting_extraction'
        FROM (
            SELECT DISTINCT ON (candidate_id)
                candidate_id, extract_state, extract_status, extract_document_uuid
            FROM hr_applicant
            WHERE candidate_id IS NOT NULL
                AND coalesce(extract_state, 'no_extract_requested')
                    <> 'no_extract_requested'
            ORDER BY candidate_id, id DESC
        ) applicant
        WHERE applicant.candidate_id = candidate.id
            AND candidate.extract_state = 'no_extract_requested'
            AND candidate.extract_document_uuid IS NULL
        """,
    )
