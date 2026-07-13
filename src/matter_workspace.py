from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from models import LegalOpsAssessment


class MatterVaultRecord(BaseModel):
    id: str
    kind: Literal["intake", "source", "finding", "control", "review_packet"]
    label: str
    provenance_ref: str
    status: Literal["verified", "review_required", "blocked"]


class MatterVault(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_id: Literal["legal-ops-agent.matter-vault.v1"] = Field(
        "legal-ops-agent.matter-vault.v1", alias="schema"
    )
    assessment_id: str
    records: list[MatterVaultRecord]
    access_mode: Literal["internal_review"] = "internal_review"
    external_action_allowed: bool = Field(False, alias="externalActionAllowed")


class WorkflowAgentDefinition(BaseModel):
    id: str
    label: str
    objective: str
    input_refs: list[str]
    steps: list[str]
    output_artifact: str
    review_gate: str
    external_action_allowed: bool = False


class WorkflowAgentLibrary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_id: Literal["legal-ops-agent.workflow-library.v1"] = Field(
        "legal-ops-agent.workflow-library.v1", alias="schema"
    )
    agents: list[WorkflowAgentDefinition]
    execution_mode: Literal["deterministic_supervised"] = "deterministic_supervised"
    external_action_allowed: bool = Field(False, alias="externalActionAllowed")


class SharedReviewPermission(BaseModel):
    role: Literal["matter_owner", "specialist_reviewer", "business_requester"]
    access: Literal["manage", "review", "approved_summary_only"]
    status: Literal["active", "pending_approval"]


class SharedReviewRoom(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_id: Literal["legal-ops-agent.shared-review-room.v1"] = Field(
        "legal-ops-agent.shared-review-room.v1", alias="schema"
    )
    room_id: str
    permissions: list[SharedReviewPermission]
    visible_record_ids: list[str]
    audit_events_required: list[str]
    external_access_enabled: bool = Field(False, alias="externalAccessEnabled")
    activation_gate: str


class MatterWorkspace(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_id: Literal["legal-ops-agent.matter-workspace.v1"] = Field(
        "legal-ops-agent.matter-workspace.v1", alias="schema"
    )
    vault: MatterVault
    workflow_library: WorkflowAgentLibrary = Field(alias="workflowLibrary")
    shared_review_room: SharedReviewRoom = Field(alias="sharedReviewRoom")
    export_allowed: bool = Field(alias="exportAllowed")
    external_action_allowed: bool = Field(False, alias="externalActionAllowed")


def build_matter_workspace(assessment: LegalOpsAssessment) -> MatterWorkspace:
    records = [
        MatterVaultRecord(
            id="intake",
            kind="intake",
            label=assessment.matter.title,
            provenance_ref=f"assessment:{assessment.assessment_id}:intake",
            status="review_required",
        )
    ]
    records.extend(
        MatterVaultRecord(
            id=f"source-{index}",
            kind="source",
            label=source.source_ref,
            provenance_ref=source.source_ref,
            status=(
                "verified"
                if source.status == "pass"
                else "blocked" if source.status == "blocker" else "review_required"
            ),
        )
        for index, source in enumerate(assessment.source_verifications, start=1)
    )
    records.extend(
        MatterVaultRecord(
            id=f"finding-{index}",
            kind="finding",
            label=finding.summary,
            provenance_ref=f"assessment:{assessment.assessment_id}:finding:{index}",
            status="blocked" if finding.severity == "blocker" else "review_required",
        )
        for index, finding in enumerate(assessment.findings, start=1)
    )
    records.extend(
        MatterVaultRecord(
            id=f"control-{control.control_id}",
            kind="control",
            label=control.summary,
            provenance_ref=f"assessment:{assessment.assessment_id}:control:{control.control_id}",
            status=(
                "verified"
                if control.status == "pass"
                else "blocked" if control.status == "blocker" else "review_required"
            ),
        )
        for control in assessment.controls
    )
    vault = MatterVault(
        schema="legal-ops-agent.matter-vault.v1",
        assessment_id=assessment.assessment_id,
        records=records,
        externalActionAllowed=False,
    )
    library = WorkflowAgentLibrary(
        schema="legal-ops-agent.workflow-library.v1",
        agents=_workflow_agents(assessment),
        externalActionAllowed=False,
    )
    visible_record_ids = [record.id for record in records if record.status == "verified"]
    room = SharedReviewRoom(
        schema="legal-ops-agent.shared-review-room.v1",
        room_id=f"room-{assessment.assessment_id}",
        permissions=[
            SharedReviewPermission(role="matter_owner", access="manage", status="active"),
            SharedReviewPermission(role="specialist_reviewer", access="review", status="active"),
            SharedReviewPermission(
                role="business_requester",
                access="approved_summary_only",
                status="pending_approval",
            ),
        ],
        visible_record_ids=visible_record_ids,
        audit_events_required=[
            "access_requested",
            "access_approved",
            "record_shared",
            "review_decision_recorded",
            "access_revoked",
        ],
        externalAccessEnabled=False,
        activation_gate=(
            "A legal reviewer must approve the business-requester summary and access scope."
        ),
    )
    return MatterWorkspace(
        schema="legal-ops-agent.matter-workspace.v1",
        vault=vault,
        workflowLibrary=library,
        sharedReviewRoom=room,
        exportAllowed=assessment.export_allowed,
        externalActionAllowed=False,
    )


def _workflow_agents(assessment: LegalOpsAssessment) -> list[WorkflowAgentDefinition]:
    base_refs = [f"assessment:{assessment.assessment_id}"]
    return [
        WorkflowAgentDefinition(
            id="matter-triage",
            label="Matter triage",
            objective="Validate intake, determine risk and route the matter.",
            input_refs=base_refs,
            steps=["validate intake", "score deterministic risks", "select reviewer route"],
            output_artifact="typed assessment",
            review_gate="Consequential routing remains subject to human review.",
        ),
        WorkflowAgentDefinition(
            id="source-verification",
            label="Source verification",
            objective="Apply local source-boundary controls to every reference.",
            input_refs=[source.source_ref for source in assessment.source_verifications],
            steps=["classify source prefix", "apply allowlist", "surface blockers"],
            output_artifact="source verification report",
            review_gate="Public sources require review and blocked prefixes stop export.",
        ),
        WorkflowAgentDefinition(
            id="review-packet",
            label="Review packet preparation",
            objective="Assemble findings, controls and review evidence into a draft packet.",
            input_refs=base_refs,
            steps=[
                "assemble findings",
                "attach provenance",
                "verify audit chain",
                "apply export gate",
            ],
            output_artifact="draft review packet",
            review_gate="A documented human approval and intact audit chain are required.",
        ),
    ]
