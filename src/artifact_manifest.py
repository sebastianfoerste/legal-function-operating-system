from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from models import LegalOpsAssessment
from src.legal_ops import utc_now_iso

MANIFEST_SCHEMA = "legal-ops-agent.artifact-manifest.v1"


def _bytes_for_artifact(artifact: Any) -> bytes:
    if isinstance(artifact, Path):
        return artifact.read_bytes()
    if isinstance(artifact, bytes):
        return artifact
    if isinstance(artifact, str):
        return artifact.encode("utf-8")
    return json.dumps(
        artifact,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_artifact_manifest(
    assessment: LegalOpsAssessment,
    artifacts: dict[str, Any],
) -> dict[str, Any]:
    """Build a local integrity manifest for generated review artifacts."""

    entries: list[dict[str, Any]] = []
    for name, artifact in sorted(artifacts.items()):
        data = _bytes_for_artifact(artifact)
        entry: dict[str, Any] = {
            "name": name,
            "sha256": _sha256(data),
            "bytes": len(data),
        }
        if isinstance(artifact, Path):
            entry["path"] = str(artifact)
        entries.append(entry)

    signature_input = {
        "schema": MANIFEST_SCHEMA,
        "assessment_id": assessment.assessment_id,
        "review_state": assessment.review_state,
        "export_allowed": assessment.export_allowed,
        "artifacts": entries,
    }
    signature_payload = json.dumps(
        signature_input,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return {
        "schema": MANIFEST_SCHEMA,
        "assessment_id": assessment.assessment_id,
        "matter_title": assessment.matter.title,
        "generated_at_utc": utc_now_iso(),
        "review_state": assessment.review_state,
        "export_allowed": assessment.export_allowed,
        "artifacts": entries,
        "local_integrity_signature": {
            "algorithm": "sha256",
            "value": _sha256(signature_payload),
            "note": "Local artifact integrity digest. This is not an eIDAS signature.",
        },
    }


def write_artifact_manifest(
    assessment: LegalOpsAssessment,
    output_path: Path,
    artifacts: dict[str, Any],
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_artifact_manifest(assessment, artifacts)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output_path
