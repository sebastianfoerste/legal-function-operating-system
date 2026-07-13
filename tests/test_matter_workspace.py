from models import ReviewDecision
from src.legal_ops import apply_review_decision, assess_matter, build_sample_matter
from src.matter_workspace import build_matter_workspace


def test_workspace_builds_provenance_bound_matter_vault():
    workspace = build_matter_workspace(assess_matter(build_sample_matter()))
    assert workspace.vault.schema_id == "legal-ops-agent.matter-vault.v1"
    assert workspace.vault.records
    assert all(record.provenance_ref for record in workspace.vault.records)
    assert workspace.vault.external_action_allowed is False


def test_approved_intake_is_promoted_to_verified_state():
    assessment = assess_matter(build_sample_matter())
    approved = apply_review_decision(
        assessment,
        ReviewDecision(
            reviewer="Legal reviewer",
            state="approved",
            note="Approved after source and control review was completed.",
        ),
    )
    workspace = build_matter_workspace(approved)
    assert workspace.vault.records[0].status == "verified"


def test_workspace_exposes_reusable_supervised_workflow_agents():
    workspace = build_matter_workspace(assess_matter(build_sample_matter()))
    assert [agent.id for agent in workspace.workflow_library.agents] == [
        "matter-triage",
        "source-verification",
        "review-packet",
    ]
    assert all(agent.review_gate for agent in workspace.workflow_library.agents)
    assert all(
        agent.external_action_allowed is False for agent in workspace.workflow_library.agents
    )


def test_shared_review_room_keeps_requester_access_pending():
    workspace = build_matter_workspace(assess_matter(build_sample_matter()))
    requester = next(
        permission
        for permission in workspace.shared_review_room.permissions
        if permission.role == "business_requester"
    )
    assert requester.status == "pending_approval"
    assert requester.access == "approved_summary_only"
    assert workspace.shared_review_room.external_access_enabled is False
    assert workspace.external_action_allowed is False
