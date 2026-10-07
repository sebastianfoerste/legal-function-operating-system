"""Command line for one reviewer pilot: prepare a draft, hold sessions, export the record.

Every command reads and rewrites local JSON files. Nothing is sent anywhere.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from pathlib import Path

from models import MatterIntake
from src.export_gate import ExportBlockedError
from src.matter_documents import FAILED_STATUSES, manifest_differences, verify_matter_documents
from src.pilot.evidence.harness_review import load_harness_review, template_differences
from src.pilot.evidence.record import (
    build_pilot_record,
    render_recommendations,
    render_reviewed_recommendations,
    write_pilot_record,
)
from src.pilot.evidence.session import (
    PilotReviewDraft,
    PilotReviewSession,
    close_review_session,
    mark_draft_reviewable,
    prepare_review_draft,
    record_material_omission,
    record_recommendation_decision,
    start_review_session,
)
from src.review_packet import write_review_packet


def _load_matter(path: Path) -> MatterIntake:
    return MatterIntake.model_validate_json(path.read_text(encoding="utf-8"))


def _load_draft(path: Path) -> PilotReviewDraft:
    return PilotReviewDraft.model_validate_json(path.read_text(encoding="utf-8"))


def _load_session(path: Path) -> PilotReviewSession:
    return PilotReviewSession.model_validate_json(path.read_text(encoding="utf-8"))


def _chain_root(session: PilotReviewSession) -> str:
    return session.assessment.audit_events[-1].event_hash


def _write(path: Path, model: PilotReviewDraft | PilotReviewSession) -> None:
    text = model.model_dump_json(by_alias=True, indent=2) + "\n"
    # A file that cannot be read back must never replace one that can.
    type(model).model_validate_json(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written beside the target and moved into place, so an interrupted command
    # cannot leave half a session file behind.
    temporary = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _update(
    path: Path, step: Callable[[PilotReviewSession], PilotReviewSession]
) -> PilotReviewSession:
    session = _load_session(path)
    updated = step(session)
    # Another command may have written meanwhile; its event must not be overwritten.
    if _chain_root(_load_session(path)) != _chain_root(session):
        raise ValueError(f"{path} changed while this command ran; run the command again")
    _write(path, updated)
    return updated


def _verify_documents(args: argparse.Namespace) -> int:
    matter = _load_matter(args.input)
    records = verify_matter_documents(matter, args.documents_root)
    for record in records:
        print(f"{record.status}: {record.document_id} ({record.path})")
    differences: list[str] = []
    if args.harness_manifest:
        manifest = json.loads(args.harness_manifest.read_text(encoding="utf-8"))
        try:
            differences = manifest_differences(matter, manifest)
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError(f"{args.harness_manifest} is not a matter manifest") from error
        for difference in differences:
            print(f"manifest difference: {difference}")
    failed = [record for record in records if record.status in FAILED_STATUSES]
    return 1 if failed or differences else 0


def _prepare(args: argparse.Namespace) -> int:
    target = args.out_dir / "draft.json"
    if target.exists():
        # A second draft has a different audit chain; sessions held on the first
        # one could never be exported against it.
        raise ValueError(f"{target} already exists; a draft is prepared once per round")
    matter = _load_matter(args.input)
    review = load_harness_review(args.harness_review) if args.harness_review else None
    if args.harness_template:
        if review is None:
            raise ValueError("--harness-template is checked against --harness-review")
        template = json.loads(args.harness_template.read_text(encoding="utf-8"))
        differences = template_differences(review, matter, template)
        if differences:
            raise ValueError(f"the review is not the one the template names: {differences}")
    draft = prepare_review_draft(matter, documents_root=args.documents_root, harness_review=review)
    _write(target, draft)
    write_review_packet(draft.assessment, args.out_dir / "review-packet.md")
    (args.out_dir / "recommendations.md").write_text(
        render_recommendations(draft), encoding="utf-8"
    )
    print(f"draft ready ({draft.review_source}): {draft.review_sha256}")
    for item in draft.recommendation_set.recommendations:
        print(f"{item.id}: {item.proposed_text}")
    return 0


def _start(args: argparse.Namespace) -> int:
    if args.session.exists():
        raise ValueError(f"{args.session} already exists; a session is started once")
    session = start_review_session(
        _load_draft(args.draft),
        reviewer_id=args.reviewer,
        evidence_class=args.evidence_class,
        reviewer_profile=args.profile,
    )
    _write(args.session, session)
    print(f"session started: {session.session_id}")
    return 0


def _reviewable(args: argparse.Namespace) -> int:
    _update(args.session, mark_draft_reviewable)
    return 0


def _decide(args: argparse.Namespace) -> int:
    _update(
        args.session,
        lambda session: record_recommendation_decision(
            session,
            recommendation_id=args.recommendation,
            decision=args.decision,
            usefulness=args.usefulness,
            reason=args.reason,
            corrected_text=args.corrected_text,
        ),
    )
    return 0


def _omission(args: argparse.Namespace) -> int:
    _update(args.session, lambda session: record_material_omission(session, text=args.text))
    return 0


def _close(args: argparse.Namespace) -> int:
    session = _update(
        args.session,
        lambda session: close_review_session(
            session,
            state=args.state,
            note=args.note,
            declared_review_minutes=args.declared_review_minutes,
            workflow_feedback=args.feedback,
        ),
    )
    print(f"session closed: export_allowed={str(session.assessment.export_allowed).lower()}")
    # The one value that, kept outside this file, later proves the file was not cut back.
    print(f"audit chain root: {_chain_root(session)}")
    return 0


def _export(args: argparse.Namespace) -> int:
    draft = _load_draft(args.draft)
    if args.documents_root:
        changed = [
            f"{record.document_id}: {record.status}"
            for record in verify_matter_documents(draft.assessment.matter, args.documents_root)
            if record.status != "verified"
        ]
        if changed:
            raise ValueError(f"documents changed since the draft was prepared: {changed}")
    sessions = [_load_session(path) for path in args.session]
    json_path, markdown_path = write_pilot_record(build_pilot_record(draft, sessions), args.out_dir)
    print(f"wrote {json_path} and {markdown_path}")
    for session in sessions:
        # The export gate decides. This command only reports what it said.
        try:
            text = render_reviewed_recommendations(session)
        except ExportBlockedError as blocked:
            print(f"{session.reviewer_id}: no revised draft. {blocked}")
            continue
        revised = args.out_dir / f"reviewed-recommendations-{session.reviewer_id}.md"
        revised.write_text(text, encoding="utf-8")
        print(f"wrote {revised}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a bounded reviewer pilot on one matter.")
    commands = parser.add_subparsers(dest="command", required=True)

    verify = commands.add_parser("verify-documents", help="Check intake documents by hash.")
    verify.add_argument("--input", type=Path, required=True)
    verify.add_argument("--documents-root", type=Path, required=True)
    verify.add_argument("--harness-manifest", type=Path)
    verify.set_defaults(handler=_verify_documents)

    prepare = commands.add_parser("prepare", help="Assess the matter and fix the review draft.")
    prepare.add_argument("--input", type=Path, required=True)
    prepare.add_argument("--documents-root", type=Path)
    prepare.add_argument(
        "--harness-review",
        type=Path,
        help="Review output or capture from contract-review-eval-harness to put to reviewers.",
    )
    prepare.add_argument(
        "--harness-template",
        type=Path,
        help="Session template the harness wrote for that review; checked against it.",
    )
    prepare.add_argument("--out-dir", type=Path, required=True)
    prepare.set_defaults(handler=_prepare)

    start = commands.add_parser("start", help="Start one reviewer's session on the draft.")
    start.add_argument("--draft", type=Path, required=True)
    start.add_argument("--session", type=Path, required=True)
    start.add_argument("--reviewer", required=True, help="Pseudonym such as R01.")
    start.add_argument(
        "--evidence-class",
        required=True,
        choices=["practising_lawyer", "author_self_review", "synthetic_example"],
    )
    start.add_argument("--profile", default="")
    start.set_defaults(handler=_start)

    reviewable = commands.add_parser("reviewable", help="Mark the draft as reviewable.")
    reviewable.add_argument("--session", type=Path, required=True)
    reviewable.set_defaults(handler=_reviewable)

    decide = commands.add_parser("decide", help="Record a decision on one recommendation.")
    decide.add_argument("--session", type=Path, required=True)
    decide.add_argument("--recommendation", required=True)
    decide.add_argument("--decision", required=True, choices=["accepted", "corrected", "rejected"])
    decide.add_argument("--usefulness", type=int, required=True, choices=[1, 2, 3, 4])
    decide.add_argument("--reason", default="")
    decide.add_argument("--corrected-text")
    decide.set_defaults(handler=_decide)

    omission = commands.add_parser("omission", help="Record a material omission.")
    omission.add_argument("--session", type=Path, required=True)
    omission.add_argument("--text", required=True)
    omission.set_defaults(handler=_omission)

    close = commands.add_parser("close", help="Decide the matter and close the session.")
    close.add_argument("--session", type=Path, required=True)
    close.add_argument(
        "--state",
        required=True,
        choices=["approved", "rejected", "revision_requested", "escalated"],
    )
    close.add_argument("--note", required=True)
    close.add_argument("--declared-review-minutes", type=float)
    close.add_argument("--feedback", default="")
    close.set_defaults(handler=_close)

    export = commands.add_parser("export", help="Write the pilot record and revised drafts.")
    export.add_argument("--draft", type=Path, required=True)
    export.add_argument("--session", type=Path, action="append", default=[])
    export.add_argument("--documents-root", type=Path, help="Check the documents again.")
    export.add_argument("--out-dir", type=Path, required=True)
    export.set_defaults(handler=_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, OSError) as error:
        print(f"refused: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
