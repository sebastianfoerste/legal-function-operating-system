"""Hash verification for the documents a matter intake references in place."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from models import (
    DocumentVerificationRecord,
    DocumentVerificationStatus,
    MatterDocument,
    MatterIntake,
)

FAILED_STATUSES = frozenset({"mismatch", "missing", "refused"})


def _record(
    document: MatterDocument,
    status: DocumentVerificationStatus,
    reason: str,
    actual_sha256: str | None = None,
) -> DocumentVerificationRecord:
    return DocumentVerificationRecord(
        document_id=document.document_id,
        kind=document.kind,
        path=document.path,
        expected_sha256=document.sha256,
        actual_sha256=actual_sha256,
        status=status,
        reason=reason,
    )


def verify_matter_document(
    document: MatterDocument, documents_root: Path | None
) -> DocumentVerificationRecord:
    """Check one document against its recorded hash without reading it as text."""

    if documents_root is None:
        return _record(
            document, "not_checked", "No documents root was supplied, so the hash was not checked."
        )
    root = documents_root.resolve()
    target = (root / document.path).resolve()
    # A symlink inside the root can still point outside it.
    if not target.is_relative_to(root):
        return _record(document, "refused", "The path resolves outside the documents root.")
    if not target.is_file():
        return _record(document, "missing", "No file exists at this path under the documents root.")
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != document.sha256:
        return _record(
            document,
            "mismatch",
            "The file differs from the version the intake recorded.",
            actual_sha256=actual,
        )
    return _record(
        document, "verified", "The file matches the hash the intake recorded.", actual_sha256=actual
    )


def verify_matter_documents(
    matter: MatterIntake, documents_root: Path | None
) -> list[DocumentVerificationRecord]:
    return [verify_matter_document(document, documents_root) for document in matter.documents]


def manifest_differences(matter: MatterIntake, manifest: dict[str, Any]) -> list[str]:
    """Compare an intake with a contract-review-eval matter manifest.

    The intake mirrors the manifest by hand. This reports every point where the two
    have drifted, and every manifest document of the intake's round that is absent.
    """

    differences: list[str] = []
    if matter.matter_id != manifest.get("matter_id"):
        differences.append(
            f"matter_id: intake {matter.matter_id!r}, manifest {manifest.get('matter_id')!r}"
        )
    manifest_documents = {item["document_id"]: item for item in manifest.get("documents", [])}
    for document in matter.documents:
        expected = manifest_documents.get(document.document_id)
        if expected is None:
            differences.append(f"{document.document_id}: not in the manifest")
            continue
        for field in ("kind", "path", "sha256", "introduced_in"):
            if getattr(document, field) != expected.get(field):
                differences.append(
                    f"{document.document_id}.{field}: intake {getattr(document, field)!r}, "
                    f"manifest {expected.get(field)!r}"
                )
    rounds = [item["round_id"] for item in manifest.get("rounds", [])]
    if matter.round_id not in rounds:
        differences.append(f"round_id {matter.round_id!r} is not a round of the manifest")
        return differences
    # Rounds accumulate: a round's file holds every document introduced up to it.
    in_scope = set(rounds[: rounds.index(matter.round_id) + 1])
    intake_ids = {document.document_id for document in matter.documents}
    for document_id, expected in manifest_documents.items():
        in_round = expected.get("introduced_in") in in_scope
        if in_round and document_id not in intake_ids:
            differences.append(f"{document_id}: in the manifest for this round, not in the intake")
        if not in_round and document_id in intake_ids:
            differences.append(f"{document_id}: introduced after round {matter.round_id}")
    return differences
