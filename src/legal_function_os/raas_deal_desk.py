"""Stable public facade for the industrial robotics RaaS deal desk."""

from legal_function_os.raas_models import (
    RAAS_INPUT_SCHEMA,
    ClauseReview,
    CounselBrief,
    FinanceIssue,
    HundredDayPhase,
    RaaSDealPack,
    RegulatoryItem,
    validate_raas_deal,
)
from legal_function_os.raas_renderers import (
    render_raas_html,
    render_raas_markdown,
    render_raas_svg,
    write_raas_outputs,
)
from legal_function_os.raas_rules import build_raas_deal_pack
from legal_function_os.raas_sources import (
    DISCLAIMER,
    SOURCE_MANIFEST,
    VERIFIED_ON,
    source_digest,
)

__all__ = [
    "RAAS_INPUT_SCHEMA",
    "VERIFIED_ON",
    "DISCLAIMER",
    "SOURCE_MANIFEST",
    "ClauseReview",
    "FinanceIssue",
    "RegulatoryItem",
    "CounselBrief",
    "HundredDayPhase",
    "RaaSDealPack",
    "validate_raas_deal",
    "build_raas_deal_pack",
    "render_raas_markdown",
    "render_raas_html",
    "render_raas_svg",
    "write_raas_outputs",
    "source_digest",
]
