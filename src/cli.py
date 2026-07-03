from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Any

from models import MatterIntake, ReviewDecision, verify_audit_chain
from src.artifact_manifest import build_artifact_manifest
from src.exports import write_customer_commitment_register, write_source_verification_report
from src.legal_ops import apply_review_decision, assess_matter, build_sample_matter
from src.review_packet import write_review_packet
from src.review_packet_runner import (
    build_source_verified_review_packet_run,
    write_source_verified_review_packet_run_payload,
)
from src.trust_cockpit import (
    build_trust_cockpit,
    write_trust_cockpit_json,
    write_trust_cockpit_markdown,
)


def load_matter(path: Path | None) -> MatterIntake:
    if path is None:
        return build_sample_matter()
    return MatterIntake.model_validate_json(path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the LegalOps Agent workflow.")
    parser.add_argument("--input", type=Path, help="Path to an approved JSON matter intake file.")
    parser.add_argument("--json-output", type=Path, help="Write assessment JSON to this path.")
    parser.add_argument(
        "--packet-output", type=Path, help="Write markdown review packet to this path."
    )
    parser.add_argument(
        "--commitments-output",
        type=Path,
        help="Write the customer-commitment register JSON to this path.",
    )
    parser.add_argument(
        "--sources-output",
        type=Path,
        help="Write the source-verification report JSON to this path.",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        help="Write a local integrity manifest for generated review artifacts.",
    )
    parser.add_argument(
        "--review-runner-output",
        type=Path,
        help="Write a source-verified review packet runner JSON payload.",
    )
    parser.add_argument(
        "--trust-cockpit-output",
        type=Path,
        help="Write a source-verified trust cockpit Markdown snapshot.",
    )
    parser.add_argument(
        "--trust-cockpit-json-output",
        type=Path,
        help="Write a source-verified trust cockpit JSON snapshot.",
    )
    parser.add_argument(
        "--audit-chain-output",
        type=Path,
        help="Write the tamper-evident audit chain verification JSON to this path.",
    )
    parser.add_argument("--approve-note", help="Apply an approval note after assessment.")
    parser.add_argument(
        "--reviewer", default="General Counsel", help="Reviewer for approval notes."
    )
    return parser


def _trust_cockpit_command(args: argparse.Namespace) -> str:
    parts = ["python", "-m", "src.cli"]
    optional_paths = [
        ("--input", args.input),
        ("--json-output", args.json_output),
        ("--packet-output", args.packet_output),
        ("--commitments-output", args.commitments_output),
        ("--sources-output", args.sources_output),
        ("--review-runner-output", args.review_runner_output),
        ("--manifest-output", args.manifest_output),
        ("--audit-chain-output", args.audit_chain_output),
        ("--trust-cockpit-output", args.trust_cockpit_output),
        ("--trust-cockpit-json-output", args.trust_cockpit_json_output),
    ]
    for flag, value in optional_paths:
        if value:
            parts.extend([flag, str(value)])
    if args.approve_note:
        parts.extend(["--approve-note", args.approve_note])
        parts.extend(["--reviewer", args.reviewer])
    return " ".join(shlex.quote(part) for part in parts)


def run(args: argparse.Namespace) -> dict[str, Any]:
    matter = load_matter(args.input)
    assessment = assess_matter(matter)

    if args.approve_note:
        assessment = apply_review_decision(
            assessment,
            ReviewDecision(reviewer=args.reviewer, state="approved", note=args.approve_note),
        )

    payload = assessment.model_dump(mode="json")
    artifacts: dict[str, Any] = {"assessment_json": payload}
    source_verified_run = None
    manifest_payload = None

    def get_source_verified_run():
        nonlocal source_verified_run
        if source_verified_run is None:
            source_verified_run = build_source_verified_review_packet_run(assessment)
        return source_verified_run

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        artifacts["assessment_json"] = args.json_output
    if args.packet_output:
        write_review_packet(assessment, args.packet_output)
        artifacts["review_packet_markdown"] = args.packet_output
    if args.commitments_output:
        write_customer_commitment_register(assessment, args.commitments_output)
        artifacts["customer_commitment_register_json"] = args.commitments_output
    if args.sources_output:
        write_source_verification_report(assessment, args.sources_output)
        artifacts["source_verification_json"] = args.sources_output
    if args.review_runner_output:
        write_source_verified_review_packet_run_payload(
            get_source_verified_run(),
            args.review_runner_output,
        )
        artifacts["source_verified_review_packet_runner_json"] = args.review_runner_output
    if args.manifest_output:
        manifest_payload = build_artifact_manifest(assessment, artifacts)
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_output.write_text(
            json.dumps(manifest_payload, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.audit_chain_output:
        chain_verification = verify_audit_chain(assessment.audit_events)
        args.audit_chain_output.parent.mkdir(parents=True, exist_ok=True)
        args.audit_chain_output.write_text(
            json.dumps(chain_verification.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
        )
    if args.trust_cockpit_output or args.trust_cockpit_json_output:
        cockpit = build_trust_cockpit(
            assessment,
            source_verified_run=get_source_verified_run(),
            artifact_manifest=manifest_payload,
            fixture=str(args.input) if args.input else None,
            command=_trust_cockpit_command(args),
        )
        if args.trust_cockpit_output:
            write_trust_cockpit_markdown(cockpit, args.trust_cockpit_output)
        if args.trust_cockpit_json_output:
            write_trust_cockpit_json(cockpit, args.trust_cockpit_json_output)
    return payload


def main() -> None:
    payload = run(build_parser().parse_args())
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
