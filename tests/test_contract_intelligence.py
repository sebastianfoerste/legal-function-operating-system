import unittest

from legal_function_os.contract_intelligence import DPA_PLAYBOOK, build_dpa_review


def document(clauses):
    return {"id": "dpa-1", "title": "AVV HelpDeskCo", "clauses": clauses}


class DpaPlaybookTests(unittest.TestCase):
    def test_playbook_covers_all_eight_letters(self):
        self.assertEqual(len(DPA_PLAYBOOK), 8)
        for letter in "abcdefgh":
            self.assertTrue(any(f"lit. {letter}" in requirement["citation"] for requirement in DPA_PLAYBOOK))
        self.assertTrue(all(requirement["required"] for requirement in DPA_PLAYBOOK))

    def test_pattern_hit_passes_and_carries_citation(self):
        review = build_dpa_review([document({"audit_rights": "Der Verantwortliche kann Audits und Inspektionen durchführen."})])
        row = next(row for row in review["rows"] if row["requirement_key"] == "audit_rights")
        self.assertEqual(row["status"], "pass")
        self.assertIn("lit. h", row["citation"])

    def test_clause_without_pattern_needs_review(self):
        row = next(row for row in build_dpa_review([document({"audit_rights": "Siehe Anlage 3."})])["rows"] if row["requirement_key"] == "audit_rights")
        self.assertEqual(row["status"], "review")

    def test_missing_clauses_block(self):
        review = build_dpa_review([document({})])
        self.assertEqual(review["blocker_count"], 8)
        self.assertTrue(review["requires_human_review"])
        self.assertFalse(review["external_action_allowed"])

    def test_multiple_documents_get_independent_rows(self):
        review = build_dpa_review([document({}), {"id": "dpa-2", "title": "AVV CloudCo", "clauses": {"deletion_return": "Löschung nach Vertragsende."}}])
        self.assertEqual(len(review["rows"]), 16)
        self.assertEqual(sum(row["status"] == "missing" for row in review["rows"] if row["document_id"] == "dpa-2"), 7)


if __name__ == "__main__":
    unittest.main()
