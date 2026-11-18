# Message drafts

Source: bundled synthetic message export. Policy: Default illustrative policy. 6 drafts from 6 messages; 5 have blanks for legal to fill before validate and triage.

Drafts for legal to complete. Nothing was sent and nothing was decided: no risk, priority, queue, service level or approval chain. Values were copied only from labelled lines such as `Value band: <50k`; nothing was read from the rest of a message. Senders are copied as written in the export and are not verified: a `syn-` sender marks the export as synthetic, and it says nothing about who sent a message. Not legal advice.

## REQ-DRAFT-1: NDA: Initech Design (synthetic)

Message syn-msg-0001 (line 1) from syn-sales-ana, in legal-requests (synthetic chat channel), sent 2026-11-16T09:12:00Z.

    Hi legal, please review the NDA with Initech Design.
    Request type: commercial_contract
    Counterparty: Initech Design (synthetic)
    Value band: <50k
    Personal data: no
    Non-EEA transfer: no
    Uncapped liability: no
    Urgency: low
    Requested by: sales

Copied:

- `title`: NDA: Initech Design (synthetic) (from the subject)
- `type`: commercial_contract
- `counterparty`: Initech Design (synthetic)
- `value_band`: <50k
- `personal_data`: false
- `non_eea_transfer`: false
- `uncapped_liability`: false
- `urgency`: low
- `requested_by`: sales

Blank for legal to fill: none.

Not given: `deadline`.

## REQ-DRAFT-2: DPA: support tool sub-processor (synthetic)

Message syn-msg-0002 (line 2) from syn-product-ben, in legal-requests (synthetic mailbox), sent 2026-11-16T10:40:00Z.

    Type: dpa
    Counterparty: Support Tools LLC (synthetic)
    Personal data: ja
    Deadline: 2026-12-04
    We are not sure where their support staff sit.

Copied:

- `title`: DPA: support tool sub-processor (synthetic) (from the subject)
- `type`: dpa
- `counterparty`: Support Tools LLC (synthetic)
- `personal_data`: true
- `deadline`: 2026-12-04

Blank for legal to fill: `value_band`, `non_eea_transfer`, `uncapped_liability`, `urgency`.

Not given: `requested_by`.

## REQ-DRAFT-3: (no title)

Message syn-msg-0003 (line 3) from syn-sales-cara, in legal-requests (synthetic chat channel), sent 2026-11-17T08:05:00Z.

    Can someone look at the Globex MSA (synthetic)? They want uncapped liability, and EU customer data would go to their US support team. Need it by Friday.

Copied:

- none

Blank for legal to fill: `title`, `type`, `value_band`, `personal_data`, `non_eea_transfer`, `uncapped_liability`, `urgency`.

Not given: `counterparty`, `requested_by`, `deadline`.

## REQ-DRAFT-4: Renewal: analytics vendor (synthetic)

Message syn-msg-0004 (line 4) from syn-finance-dev, in legal-requests (synthetic chat channel), sent 2026-11-17T11:30:00Z.

    Value band: >1M
    Value bnad: 50k-250k
    Urgency: soon
    SLA breached: yes

Copied:

- `title`: Renewal: analytics vendor (synthetic) (from the subject)
- `value_band`: >1M
- `urgency`: soon

Blank for legal to fill: `type`, `personal_data`, `non_eea_transfer`, `uncapped_liability`.

Not given: `counterparty`, `requested_by`, `deadline`.

Check:

- error: `value_band`: '>1M' is not a value band (did you mean '>1m'?); use one of none, <50k, 50k-250k, 250k-1m, >1m
- error: `urgency`: 'soon' is not an urgency; use one of blocker, high, standard, low

Notes:

- 'Value bnad' looks like 'value_band'; not copied
- 'SLA breached' is set by legal; not copied

## REQ-DRAFT-5: Contractor agreement (synthetic)

Message syn-msg-0005 (line 5) from syn-hr-eli, in legal-requests (synthetic mailbox), sent 2026-11-17T14:00:00Z.

    Request type: employment
    Urgency: high
    Urgency: low

Copied:

- `title`: Contractor agreement (synthetic) (from the subject)
- `type`: employment

Blank for legal to fill: `value_band`, `personal_data`, `non_eea_transfer`, `uncapped_liability`, `urgency`.

Not given: `counterparty`, `requested_by`, `deadline`.

Notes:

- urgency is given 2 different ways; not copied

## REQ-DRAFT-6: Board consent for a new subsidiary (synthetic)

Message syn-msg-0006 (line 6) from syn-legalops-fay, in legal-requests (synthetic chat channel), sent 2026-11-17T16:20:00Z.

    Title: Board consent for a new subsidiary (synthetic)
    > Value band: >1m
    Request type: corporate
    Urgent: yes

Copied:

- `title`: Board consent for a new subsidiary (synthetic) (from the Title line)
- `type`: corporate

Blank for legal to fill: `value_band`, `personal_data`, `non_eea_transfer`, `uncapped_liability`, `urgency`.

Not given: `counterparty`, `requested_by`, `deadline`.

## Before triage

1. Fill every blank from the message, or by asking its sender. Do not delete a blank field: a field left out takes its default (false or none), which can lower the risk. `validate` only warns about a blank `type`, and `triage` then decides the draft without the type's own rules, which can lower the risk: fill `type` before triage.
2. Give each draft a register number in place of its `REQ-DRAFT-` id.
3. Run `legal-function-os validate` on the drafts file, then `triage`.
