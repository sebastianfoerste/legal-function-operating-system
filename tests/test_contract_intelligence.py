import json
import unittest
from importlib import resources

from legal_function_os.contract_intelligence import DPA_PLAYBOOK, build_dpa_review, render_dpa_markdown


def document(clauses):
    return {"id": "dpa-1", "title": "AVV HelpDeskCo", "clauses": clauses}


def row(review, key, document_id="dpa-1"):
    return next(
        row for row in review["rows"] if row["requirement_key"] == key and row["document_id"] == document_id
    )


def check(clauses, key):
    return row(build_dpa_review([document(clauses)]), key)


class DpaPlaybookTests(unittest.TestCase):
    def test_playbook_covers_all_eight_letters_and_the_second_subparagraph(self):
        self.assertEqual(len(DPA_PLAYBOOK), 9)
        for letter in "abcdefgh":
            self.assertTrue(any(f"lit. {letter}" in requirement["citation"] for requirement in DPA_PLAYBOOK))
        letters = [requirement for requirement in DPA_PLAYBOOK if "lit." in requirement["citation"]]
        self.assertEqual(len(letters), 8)
        self.assertTrue(all(requirement["required"] for requirement in letters))
        second = DPA_PLAYBOOK[-1]
        self.assertEqual(second["citation"], "Art. 28 Abs. 3 UAbs. 2 DSGVO")
        self.assertFalse(second["required"])
        for requirement in DPA_PLAYBOOK:
            self.assertTrue(requirement["elements"])
            self.assertTrue(requirement["statute"])
            for element in requirement["elements"]:
                self.assertTrue(element["patterns"] and element["label"] and element["label_en"] and element["quote"])

    def test_complete_clause_passes_and_carries_citation(self):
        found = check(
            {"audit_rights": "Der Auftragsverarbeiter stellt alle erforderlichen Informationen zum Nachweis bereit; der Verantwortliche kann Audits und Inspektionen durchführen."},
            "audit_rights",
        )
        self.assertEqual(found["status"], "pass")
        self.assertIn("lit. h", found["citation"])
        self.assertEqual(found["missing_elements"], [])
        self.assertIn("information necessary to demonstrate compliance", found["statute"])

    def test_audits_only_clause_lacks_the_information_element(self):
        # lit. h has two elements: information to demonstrate compliance, and audits
        # including inspections. An audits-only clause used to pass.
        found = check({"audit_rights": "Der Verantwortliche kann Audits und Inspektionen durchführen."}, "audit_rights")
        self.assertEqual(found["status"], "review")
        self.assertEqual(found["missing_elements"], ["information_to_demonstrate_compliance"])
        information_only = check(
            {"audit_rights": "The processor makes available all information necessary to demonstrate compliance."},
            "audit_rights",
        )
        self.assertEqual(information_only["status"], "review")
        self.assertEqual(information_only["missing_elements"], ["audits_and_inspections"])

    def test_clause_without_pattern_needs_review(self):
        found = check({"audit_rights": "Siehe Anlage 3."}, "audit_rights")
        self.assertEqual(found["status"], "review")
        self.assertEqual(
            found["missing_elements"], ["information_to_demonstrate_compliance", "audits_and_inspections"]
        )

    def test_missing_clauses_block(self):
        review = build_dpa_review([document({})])
        self.assertEqual(review["blocker_count"], 8)
        self.assertEqual(review["schema"], "legal-function-os.dpa-review.v1")
        self.assertTrue(review["requires_human_review"])
        self.assertFalse(review["external_action_allowed"])
        missing = row(review, "documented_instructions")
        self.assertEqual(missing["status"], "missing")
        self.assertEqual(missing["missing_elements"], ["documented_instructions", "third_country_transfers"])

    def test_multiple_documents_get_independent_rows(self):
        review = build_dpa_review([document({}), {"id": "dpa-2", "title": "AVV CloudCo", "clauses": {"deletion_return": "Löschung nach Vertragsende."}}])
        self.assertEqual(len(review["rows"]), 18)
        self.assertEqual(sum(row["status"] == "missing" for row in review["rows"] if row["document_id"] == "dpa-2"), 7)
        self.assertEqual(row(review, "deletion_return", "dpa-2")["status"], "pass")


class StatutoryElementTests(unittest.TestCase):
    def test_lit_a_needs_the_third_country_transfer_wording(self):
        english = check(
            {"documented_instructions": "The processor shall process personal data only on documented instructions from the controller."},
            "documented_instructions",
        )
        self.assertEqual(english["status"], "review")
        self.assertEqual(english["missing_elements"], ["third_country_transfers"])
        complete = check(
            {"documented_instructions": "The processor processes personal data only on documented instructions from the controller, including with regard to transfers to a third country or an international organisation."},
            "documented_instructions",
        )
        self.assertEqual(complete["status"], "pass")
        german = check(
            {"documented_instructions": "Verarbeitung nur auf dokumentierte Weisung des Verantwortlichen, auch bei Übermittlungen in ein Drittland."},
            "documented_instructions",
        )
        self.assertEqual(german["status"], "pass")

    def test_lit_f_needs_breach_notification_and_dpia_or_prior_consultation(self):
        breach_only = check(
            {"breach_and_dpia_assistance": "The processor notifies the controller without undue delay after becoming aware of a personal data breach."},
            "breach_and_dpia_assistance",
        )
        self.assertEqual(breach_only["status"], "review")
        self.assertEqual(breach_only["missing_elements"], ["dpia_and_prior_consultation"])
        self.assertEqual(breach_only["negated_elements"], [])  # "without undue delay" is a deadline
        dpia_only = check(
            {"breach_and_dpia_assistance": "Der Auftragsverarbeiter unterstützt bei einer Datenschutz-Folgenabschätzung und der vorherigen Konsultation der Aufsichtsbehörde."},
            "breach_and_dpia_assistance",
        )
        self.assertEqual(dpia_only["status"], "review")
        self.assertEqual(dpia_only["missing_elements"], ["breach_notification"])
        both = check(
            {"breach_and_dpia_assistance": "The processor assists with personal data breach notifications and with any data protection impact assessment."},
            "breach_and_dpia_assistance",
        )
        self.assertEqual(both["status"], "pass")
        self.assertEqual(DPA_PLAYBOOK[5]["label"], "Unterstützung bei den Pflichten nach Art. 32 bis 36 DSGVO")

    def test_lit_f_reference_to_the_whole_range_satisfies_every_element(self):
        for text in (
            "The processor assists the controller with its obligations under Articles 32 to 36.",
            "Der Auftragsverarbeiter unterstützt den Verantwortlichen bei den Pflichten nach Art. 32 bis 36 DSGVO.",
            "Assistance with the obligations pursuant to Arts. 32-36 GDPR.",
        ):
            found = check({"breach_and_dpia_assistance": text}, "breach_and_dpia_assistance")
            self.assertEqual(found["status"], "pass", text)
            self.assertEqual([element["status"] for element in found["elements"]], ["found", "found"])

    def test_second_subparagraph_row_is_review_when_absent_and_never_a_blocker(self):
        review = build_dpa_review([document({})])
        absent = row(review, "unlawful_instruction_notice")
        self.assertEqual(absent["status"], "review")
        self.assertFalse(absent["required"])
        self.assertEqual(absent["missing_elements"], ["informs_of_infringing_instruction"])
        self.assertEqual(review["blocker_count"], 8)
        english = check(
            {"unlawful_instruction_notice": "The processor shall immediately inform the controller if, in its opinion, an instruction infringes the GDPR."},
            "unlawful_instruction_notice",
        )
        self.assertEqual(english["status"], "pass")
        german = check(
            {"unlawful_instruction_notice": "Der Auftragsverarbeiter informiert den Verantwortlichen unverzüglich, falls eine Weisung gegen die DSGVO verstößt."},
            "unlawful_instruction_notice",
        )
        self.assertEqual(german["status"], "pass")
        unrelated = check({"unlawful_instruction_notice": "Instructions are given in writing."}, "unlawful_instruction_notice")
        self.assertEqual(unrelated["status"], "review")


class NegationAndWordBoundaryTests(unittest.TestCase):
    def test_negated_english_clause_is_review_not_pass(self):
        found = check(
            {"audit_rights": "The processor makes available all information necessary to demonstrate compliance but does not allow audits or inspections."},
            "audit_rights",
        )
        self.assertEqual(found["status"], "review")
        self.assertEqual(found["negated_elements"], ["audits_and_inspections"])
        self.assertEqual(found["missing_elements"], [])
        self.assertIn("Überprüfungen einschließlich Inspektionen (negated)", render_dpa_markdown(build_dpa_review([document({"audit_rights": "The controller has no audit rights."})])))

    def test_negated_german_clause_is_review_not_pass(self):
        found = check(
            {"audit_rights": "Der Verantwortliche erhält keine Überprüfungs- oder Inspektionsrechte; Nachweise werden bereitgestellt."},
            "audit_rights",
        )
        self.assertEqual(found["status"], "review")
        self.assertEqual(found["negated_elements"], ["audits_and_inspections"])
        self.assertEqual(found["missing_elements"], [])
        without = check({"deletion_return": "Die Daten werden ohne Löschung weiter gespeichert."}, "deletion_return")
        self.assertEqual(without["status"], "review")
        self.assertEqual(without["negated_elements"], ["deletion_or_return"])

    def test_negation_is_not_read_across_a_sentence_boundary(self):
        found = check(
            {"audit_rights": "The controller has no further duties. Audits and inspections are allowed; all information necessary is provided."},
            "audit_rights",
        )
        self.assertEqual(found["status"], "pass")

    def test_english_terms_match_on_word_boundaries(self):
        inside = check({"deletion_return": "Data is kept on nonreturnable media."}, "deletion_return")
        self.assertEqual(inside["status"], "review")
        whole = check({"deletion_return": "At the end of the services the processor returns all personal data."}, "deletion_return")
        self.assertEqual(whole["status"], "pass")
        german_compound = check({"deletion_return": "Die Löschungsfrist beträgt dreißig Tage nach Vertragsende."}, "deletion_return")
        self.assertEqual(german_compound["status"], "pass")


class BundledAgreementsTests(unittest.TestCase):
    def setUp(self):
        self.documents = json.loads(
            resources.files("legal_function_os.data").joinpath("dpa_documents.json").read_text(encoding="utf-8")
        )
        self.review = build_dpa_review(self.documents)

    def test_dpa_001_passes_every_row(self):
        statuses = {row["requirement_key"]: row["status"] for row in self.review["rows"] if row["document_id"] == "DPA-001"}
        self.assertEqual(set(statuses.values()), {"pass"})
        self.assertEqual(len(statuses), 9)

    def test_dpa_002_shows_the_partial_clauses(self):
        statuses = {row["requirement_key"]: row["status"] for row in self.review["rows"] if row["document_id"] == "DPA-002"}
        self.assertEqual(
            statuses,
            {
                "documented_instructions": "review",
                "confidentiality_commitment": "pass",
                "security_measures": "review",
                "subprocessor_authorization": "pass",
                "data_subject_rights_assistance": "pass",
                "breach_and_dpia_assistance": "review",
                "deletion_return": "pass",
                "audit_rights": "missing",
                "unlawful_instruction_notice": "review",
            },
        )
        self.assertEqual(row(self.review, "documented_instructions", "DPA-002")["missing_elements"], ["third_country_transfers"])
        self.assertEqual(row(self.review, "breach_and_dpia_assistance", "DPA-002")["missing_elements"], ["dpia_and_prior_consultation"])
        self.assertEqual(self.review["blocker_count"], 1)

    def test_markdown_lists_the_missing_elements(self):
        markdown = render_dpa_markdown(self.review)
        self.assertIn("| Requirement | Citation | Status | Missing elements | Clause excerpt |", markdown)
        self.assertIn(
            "| Verarbeitung nur auf dokumentierte Weisung | Art. 28 Abs. 3 lit. a DSGVO | REVIEW | "
            "Einschließlich Übermittlungen in Drittländer oder an internationale Organisationen | The processor shall",
            markdown,
        )
        self.assertIn("Human review is required.", markdown)
        self.assertIn("**1** blocker (missing requirements)", markdown)


if __name__ == "__main__":
    unittest.main()
