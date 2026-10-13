"""Primary-source registry for the industrial robotics RaaS case study."""

from __future__ import annotations

import hashlib
import json

VERIFIED_ON = "2026-07-20"

DISCLAIMER = (
    "This public-safe demonstration uses synthetic facts and illustrative internal "
    "guardrails. It is legal-operations and deal-structuring support. It is not "
    "legal or accounting advice. Qualified Legal, Finance, Tax, Security, Product, "
    "and Safety reviewers must validate the analysis before any external use."
)

SOURCE_MANIFEST: tuple[dict[str, str], ...] = (
    {
        "id": "EU-DATA-ACT",
        "title": "Regulation (EU) 2023/2854, Data Act",
        "url": "https://eur-lex.europa.eu/eli/reg/2023/2854/oj/eng",
        "pinpoint": "Articles 3 to 5, 13, and 50",
        "legal_effect": "directly_applicable_regulation",
        "timing": (
            "Generally applies from 12 September 2025. Article 3(1) applies to "
            "connected products and related services placed on the market after "
            "12 September 2026."
        ),
    },
    {
        "id": "EU-MACHINERY-DIRECTIVE",
        "title": "Directive 2006/42/EC, Machinery Directive",
        "url": "https://eur-lex.europa.eu/eli/dir/2006/42/oj/eng",
        "pinpoint": "Articles 5 and 12, Annex I",
        "legal_effect": "directive_implemented_in_national_law",
        "timing": (
            "Current EU machinery framework during the synthetic 2026 review, "
            "implemented through national law."
        ),
    },
    {
        "id": "EU-MACHINERY-REGULATION",
        "title": "Regulation (EU) 2023/1230, Machinery Regulation",
        "url": "https://eur-lex.europa.eu/eli/reg/2023/1230/2026-07-27/eng",
        "pinpoint": "Articles 8, 10 to 18 and 54, Annex III",
        "legal_effect": "directly_applicable_regulation",
        "timing": (
            "Generally applies from 20 January 2027 (Article 54). Articles 26 to 42 "
            "apply from 20 January 2024. As amended by Regulation (EU) 2026/1744 "
            "(EU-AI-ACT-AMENDMENT), Article 8 requires Commission delegated acts "
            "adding health and safety requirements to Annex III for AI systems "
            "classified as high-risk under Article 6(1) of Regulation (EU) 2024/1689 "
            "as a safety component of, or as, a product covered by this Regulation. "
            "Those delegated acts are to apply by 2 August 2028."
        ),
    },
    {
        "id": "EU-AI-ACT",
        "title": "Regulation (EU) 2024/1689, Artificial Intelligence Act",
        "url": "https://eur-lex.europa.eu/eli/reg/2024/1689/2026-07-27/eng",
        "pinpoint": "Articles 2(2), 6, 9 to 15, 17, 43, and 113, Annex I",
        "legal_effect": "directly_applicable_regulation",
        "timing": (
            "Generally applies from 2 August 2026. As amended by Regulation (EU) "
            "2026/1744 (EU-AI-ACT-AMENDMENT), Chapter III, Sections 1 to 3 (except "
            "Article 6(5)) apply from 2 December 2027 for high-risk AI systems under "
            "Article 6(2) and Annex III, and from 2 August 2028 for high-risk AI "
            "systems under Article 6(1) and Annex I (Article 113(c)). The Machinery "
            "Regulation (EU) 2023/1230 is now listed in Annex I Section B. For a "
            "high-risk AI system under Article 6(1) related to machinery, only "
            "Article 6(1), Article 60a and Articles 102 to 112 apply, and Articles 57 "
            "to 59 apply only once the high-risk requirements are integrated into the "
            "Machinery Regulation (Article 2(2)); those requirements reach machinery "
            "through delegated acts under Article 8 of Regulation (EU) 2023/1230. "
            "Other phases under Article 113 must be checked separately."
        ),
    },
    {
        "id": "EU-AI-ACT-AMENDMENT",
        "title": (
            "Regulation (EU) 2026/1744 amending Regulations (EU) 2024/1689, "
            "(EU) 2018/1139 and (EU) 2023/1230 (Digital Omnibus on AI)"
        ),
        "url": "https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng",
        "pinpoint": (
            "Amendments relevant here: Articles 2(2) and 113 and Annex I of "
            "Regulation (EU) 2024/1689; Articles 8, 20 and 47 of Regulation (EU) "
            "2023/1230"
        ),
        "legal_effect": "directly_applicable_regulation",
        "timing": (
            "Published in the Official Journal on 24 July 2026 and in force from "
            "27 July 2026. Defers Chapter III, Sections 1 to 3 of Regulation (EU) "
            "2024/1689 to 2 December 2027 (Annex III) and 2 August 2028 (Article "
            "6(1), Annex I), removes the Machinery Directive 2006/42/EC from Annex I "
            "Section A and lists the Machinery Regulation (EU) 2023/1230 in Annex I "
            "Section B, and adds AI-specific delegated acts to Article 8 of "
            "Regulation (EU) 2023/1230. Effects checked against the consolidated "
            "texts of both Regulations as of 27 July 2026; confirm against the "
            "Official Journal text before external use."
        ),
    },
    {
        "id": "EU-CRA",
        "title": "Regulation (EU) 2024/2847, Cyber Resilience Act",
        "url": "https://eur-lex.europa.eu/eli/reg/2024/2847/oj/eng",
        "pinpoint": "Articles 13, 14, 32, and 71",
        "legal_effect": "directly_applicable_regulation",
        "timing": (
            "Chapter IV applies from 11 June 2026. Article 14 applies from "
            "11 September 2026. The Regulation generally applies from "
            "11 December 2027."
        ),
    },
    {
        "id": "EU-PRODUCT-LIABILITY",
        "title": "Directive (EU) 2024/2853, Product Liability Directive",
        "url": "https://eur-lex.europa.eu/eli/dir/2024/2853/oj/eng",
        "pinpoint": "Articles 2, 4, 7 to 11, 21, and 22",
        "legal_effect": "directive_requires_national_implementation",
        "timing": (
            "Member States must transpose the Directive by 9 December 2026. "
            "The resulting national rules apply to products placed on the market "
            "or put into service after 9 December 2026."
        ),
    },
    {
        "id": "EU-GDPR",
        "title": "Regulation (EU) 2016/679, General Data Protection Regulation",
        "url": "https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng",
        "pinpoint": "Articles 5, 6, 13, 28, 32, 35, and 44 to 49",
        "legal_effect": "directly_applicable_regulation",
        "timing": (
            "In force and directly applicable. The concrete obligations depend on "
            "the roles, data, purposes, and transfer path."
        ),
    },
)


def source_url(source_id: str) -> str:
    for source in SOURCE_MANIFEST:
        if source["id"] == source_id:
            return source["url"]
    raise KeyError(f"Unknown source id: {source_id}")


def source_digest() -> str:
    return hashlib.sha256(
        json.dumps(SOURCE_MANIFEST, sort_keys=True).encode("utf-8")
    ).hexdigest()
