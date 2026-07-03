from __future__ import annotations

import json

from models import ReviewDecision
from src.legal_ops import apply_review_decision, assess_matter, build_sample_matter
from src.review_packet import build_review_packet


def run_demo() -> dict[str, object]:
    matter = build_sample_matter()
    assessment = assess_matter(matter)
    reviewed = apply_review_decision(
        assessment,
        ReviewDecision(
            reviewer="General Counsel",
            state="approved",
            note=(
                "Synthetic demo approval after privacy, customer commitment and AI-governance "
                "controls were routed for review."
            ),
        ),
    )
    return {
        "initial_assessment": assessment.model_dump(mode="json"),
        "reviewed_assessment": reviewed.model_dump(mode="json"),
        "review_packet_markdown": build_review_packet(reviewed),
    }


def main() -> None:
    print(json.dumps(run_demo(), indent=2))


if __name__ == "__main__":
    main()
