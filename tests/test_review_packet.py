import re
from pathlib import Path

from src.legal_ops import assess_matter, build_sample_matter
from src.review_packet import build_review_packet


def test_review_packet_contains_controls_commitments_and_audit_trail():
    assessment = assess_matter(build_sample_matter())
    packet = build_review_packet(assessment)

    assert "# LegalOps Review Packet" in packet
    assert "## Controls" in packet
    assert "## Source Verification" in packet
    assert "## Customer Commitment Register" in packet
    assert "## Audit Trail" in packet
    assert assessment.assessment_id in packet
    assert "Export: `blocked`" in packet
    assert "review_packet_generated" in packet


def _normalise_packet(value: str) -> str:
    value = re.sub(r"loa_[a-f0-9]{16}", "loa_<hash>", value)
    return re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", "<timestamp>", value)


def test_blocked_review_packet_matches_golden_snapshot():
    packet = build_review_packet(assess_matter(build_sample_matter()))
    golden = Path("tests/goldens/review_packet_blocked.md").read_text(encoding="utf-8")

    assert _normalise_packet(packet) == golden
