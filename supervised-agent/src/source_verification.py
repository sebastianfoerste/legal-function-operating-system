from __future__ import annotations

from urllib.parse import urlparse

from models import SourceVerificationRecord

APPROVED_SOURCE_PREFIXES = ("synthetic:", "public:")
BLOCKED_SOURCE_PREFIXES = ("client:", "candidate:", "privileged:", "confidential:")
PUBLIC_REGULATORY_DOMAINS = (
    "bafin.de",
    "bundesbank.de",
    "eba.europa.eu",
    "ec.europa.eu",
    "edpb.europa.eu",
    "esma.europa.eu",
    "eur-lex.europa.eu",
    "finance.ec.europa.eu",
)


def _normalise_domain(value: str) -> str:
    return value.lower().removeprefix("www.")


def _domain_is_allowed(domain: str) -> bool:
    clean_domain = _normalise_domain(domain)
    return any(
        clean_domain == allowed or clean_domain.endswith(f".{allowed}")
        for allowed in PUBLIC_REGULATORY_DOMAINS
    )


def _public_ref_target(source_ref: str) -> str:
    return source_ref[len("public:") :].strip()


def verify_source_ref(source_ref: str) -> SourceVerificationRecord:
    """Classify one source reference without fetching external content."""

    ref = source_ref.strip()
    lower_ref = ref.lower()

    if not ref:
        return SourceVerificationRecord(
            source_ref="missing",
            category="missing",
            status="warning",
            reason="No source reference was supplied for reviewer reliance.",
            public_authority=None,
            requires_human_review=True,
        )

    if lower_ref.startswith(BLOCKED_SOURCE_PREFIXES):
        return SourceVerificationRecord(
            source_ref=ref,
            category="blocked",
            status="blocker",
            reason="Source reference uses a blocked sensitive-data prefix.",
            public_authority=None,
            requires_human_review=True,
        )

    if lower_ref.startswith("synthetic:"):
        return SourceVerificationRecord(
            source_ref=ref,
            category="synthetic",
            status="pass",
            reason="Synthetic source reference is permitted for local demo evaluation.",
            public_authority=None,
            requires_human_review=False,
        )

    if lower_ref.startswith("public:"):
        target = _public_ref_target(ref)
        parsed = urlparse(target)
        domain = _normalise_domain(parsed.netloc)
        if parsed.scheme not in {"https", "http"} or not domain:
            return SourceVerificationRecord(
                source_ref=ref,
                category="public_unapproved",
                status="warning",
                reason="Public source reference does not include a valid URL.",
                public_authority=None,
                requires_human_review=True,
            )
        if _domain_is_allowed(domain):
            return SourceVerificationRecord(
                source_ref=ref,
                category="public_regulatory",
                status="pass",
                reason="Public source domain matches the regulatory-source allowlist.",
                public_authority=domain,
                requires_human_review=True,
            )
        return SourceVerificationRecord(
            source_ref=ref,
            category="public_unapproved",
            status="warning",
            reason="Public source domain is outside the regulatory-source allowlist.",
            public_authority=domain,
            requires_human_review=True,
        )

    return SourceVerificationRecord(
        source_ref=ref,
        category="public_unapproved",
        status="warning",
        reason="Source reference uses an unapproved prefix.",
        public_authority=None,
        requires_human_review=True,
    )


def verify_source_refs(source_refs: list[str]) -> list[SourceVerificationRecord]:
    if not source_refs:
        return [verify_source_ref("")]
    return [verify_source_ref(source_ref) for source_ref in source_refs]
