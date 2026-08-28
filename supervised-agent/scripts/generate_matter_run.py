from master_orchestrator import run_demo


def main():
    demo_output = run_demo()

    # We will format a nice run log showing blocked and approved states
    initial = demo_output["initial_assessment"]
    reviewed = demo_output["reviewed_assessment"]
    packet_markdown = demo_output["review_packet_markdown"]

    matter = initial["matter"]

    content = f"""# Matter Run Log: Supervised Legal-Ops Flow

This run log shows the end-to-end flow of a high-urgency matter from intake to human approval, demonstrating the deterministic triage and the review-gate control that blocks export until signed off.

---

## 1. Matter Intake Facts

Submitted by the business team:
- **Title:** {matter["title"]}
- **Requester:** {matter["requester"]} ({matter["business_unit"]})
- **Matter Type:** {matter["matter_type"]}
- **Urgency:** {matter["urgency"]}
- **Summary:** {matter["summary"]}

---

## 2. Deterministic Triage & Risk Assessment (Export Blocked)

Upon intake, the workflow analyzes the matter facts and classifies the risk level:
- **Assessed Risk Level:** {initial["routing"]["owner_role"]} Routing Required
- **Initial Review State:** `{initial["review_state"]}`
- **Export Allowed:** `{initial["export_allowed"]}` (Blocked)

### Risk Findings Identified:
"""
    for finding in initial["findings"]:
        content += f"- **[{finding['severity'].upper()}] {finding['category']}:** {finding['summary']}\n  - *Evidence:* {finding['evidence']}\n  - *Recommended Action:* {finding['recommended_action']}\n"

    content += """
### Control Checks Applied:
"""
    for control in initial["controls"]:
        content += f"- **{control['control_id']}:** {control['status'].upper()} - {control['summary']} (Owner: {control['owner_role']})\n"

    content += f"""
---

## 3. Human Decision (Approval Recorded)

The General Counsel reviews the packet and submits the following decision:
- **Reviewer:** General Counsel
- **Decision State:** `{reviewed["review_state"]}`
- **Review Note:** "{reviewed["review_note"]}"
- **Export Allowed:** `{reviewed["export_allowed"]}` (Granted)

---

## 4. Generated Review Packet (Approved)

The final approved review packet:

{packet_markdown}
"""

    with open("examples/matter-run.md", "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")
    print("Successfully wrote examples/matter-run.md")


if __name__ == "__main__":
    main()
