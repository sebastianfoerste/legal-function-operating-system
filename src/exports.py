from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models import LegalOpsAssessment


def build_customer_commitment_register_payload(
    assessment: LegalOpsAssessment,
) -> dict[str, Any]:
    """Create a portable customer-commitment register from an assessment."""

    return {
        "assessment_id": assessment.assessment_id,
        "matter_title": assessment.matter.title,
        "review_state": assessment.review_state,
        "export_allowed": assessment.export_allowed,
        "commitments": [item.model_dump(mode="json") for item in assessment.customer_commitments],
    }


def write_customer_commitment_register(
    assessment: LegalOpsAssessment,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_customer_commitment_register_payload(assessment)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output_path


def build_source_verification_payload(assessment: LegalOpsAssessment) -> dict[str, Any]:
    """Create a portable source-verification report from an assessment."""

    return {
        "assessment_id": assessment.assessment_id,
        "matter_title": assessment.matter.title,
        "source_verifications": [
            item.model_dump(mode="json") for item in assessment.source_verifications
        ],
    }


def write_source_verification_report(
    assessment: LegalOpsAssessment,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_source_verification_payload(assessment)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output_path
