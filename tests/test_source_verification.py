import pytest

from src.source_verification import verify_source_ref, verify_source_refs


def test_verify_source_ref_accepts_public_regulatory_domain():
    record = verify_source_ref("public:https://eur-lex.europa.eu/legal-content/EN/TXT/")

    assert record.status == "pass"
    assert record.category == "public_regulatory"
    assert record.public_authority == "eur-lex.europa.eu"
    assert record.requires_human_review is True


@pytest.mark.parametrize(
    "source_ref",
    [
        "client:customer-dpa",
        "candidate:evaluation-note",
        "privileged:board-advice",
        "confidential:commercial-model",
    ],
)
def test_verify_source_ref_blocks_sensitive_prefixes(source_ref):
    record = verify_source_ref(source_ref)

    assert record.status == "blocker"
    assert record.category == "blocked"


def test_verify_source_refs_creates_missing_warning_for_empty_list():
    records = verify_source_refs([])

    assert records[0].status == "warning"
    assert records[0].category == "missing"
