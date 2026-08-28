import json
import unittest

from legal_function_os.shared_space import build_shared_space


def request(request_id="REQ-1", **overrides):
    base = {"id": request_id, "title": "DPA für neuen Subprozessor", "type": "dpa", "description": "Neuer Auftragsverarbeiter.", "facts": ["Vendor: HelpDeskCo"], "deadline": "2026-08-01"}
    base.update(overrides)
    return base


APPROVAL = {"approved_by": "GC", "note": "Statusfreigabe geprüft, keine vertraulichen Details enthalten."}


class SharedSpaceTests(unittest.TestCase):
    def test_unapproved_requests_expose_nothing_but_identity(self):
        entry = build_shared_space([request()], approvals={})["entries"][0]
        self.assertFalse(entry["shared"])
        self.assertIsNone(entry["owner_queue"])
        self.assertIsNone(entry["sla_response_hours"])

    def test_documented_approval_shares_requester_safe_fields(self):
        entry = build_shared_space([request()], approvals={"REQ-1": APPROVAL})["entries"][0]
        self.assertTrue(entry["shared"])
        self.assertEqual(entry["status"], "in_review")
        self.assertEqual(entry["next_update_due"], "2026-08-01")

    def test_short_note_does_not_count_as_documented(self):
        space = build_shared_space([request()], approvals={"REQ-1": {"approved_by": "GC", "note": "ok"}})
        self.assertFalse(space["entries"][0]["shared"])

    def test_internal_fields_never_leak(self):
        payload = json.dumps(build_shared_space([request()], approvals={"REQ-1": APPROVAL}))
        for forbidden in ("rationale", "escalations", "approval_chain", "external_counsel", '"risk"'):
            self.assertNotIn(forbidden, payload)

    def test_external_action_stays_blocked(self):
        space = build_shared_space([request()], approvals={"REQ-1": APPROVAL})
        self.assertFalse(space["external_action_allowed"])
        self.assertEqual(space["schema"], "legal-function-os.shared-space.v1")


if __name__ == "__main__":
    unittest.main()
