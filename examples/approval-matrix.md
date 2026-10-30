# Approval matrix

Policy: Default illustrative policy. The chain names who must sign off before a request can close. Every chain starts with a human reviewer, and the matrix approves nothing.

## Who is added to the chain

- Every request: Reviewer
- Value band "50k-250k" or above: Legal Ops Lead
- Value band "250k-1m" or above, or HIGH risk: General Counsel
- Value band ">1m" or above: Board note

## What sets the risk

- HIGH if any of: Personal data transferred outside the EEA; Value band ">1m" or above; Uncapped liability; A dispute at value band "250k-1m" or above.
- MEDIUM if any of: Value band "250k-1m" or above; Personal data processed; Request type corporate, fundraising, ai_governance.
- LOW otherwise.

## Chain by value band and risk

Portfolio requests are in brackets in the cell they land in.

| Value band | LOW | MEDIUM | HIGH |
| --- | --- | --- | --- |
| none | Reviewer | Reviewer (REQ-1008) | Reviewer → General Counsel (REQ-1004) |
| <50k | Reviewer (REQ-1003) | Reviewer | Reviewer → General Counsel |
| 50k-250k | Reviewer → Legal Ops Lead | Reviewer → Legal Ops Lead (REQ-1006) | Reviewer → Legal Ops Lead → General Counsel (REQ-1002) |
| 250k-1m | Not reachable | Reviewer → Legal Ops Lead → General Counsel | Reviewer → Legal Ops Lead → General Counsel (REQ-1007) |
| >1m | Not reachable | Not reachable | Reviewer → Legal Ops Lead → General Counsel → Board note (REQ-1001, REQ-1005) |

## Portfolio requests

| Request | Title | Value band | Risk | Approval chain |
| --- | --- | --- | --- | --- |
| REQ-1001 | Enterprise MSA: Globex (synthetic) | >1m | HIGH | Reviewer → Legal Ops Lead → General Counsel → Board note |
| REQ-1002 | DPA: US support sub-processor (synthetic) | 50k-250k | HIGH | Reviewer → Legal Ops Lead → General Counsel |
| REQ-1003 | NDA: design agency (synthetic) | <50k | LOW | Reviewer |
| REQ-1004 | AI feature governance review: agent autonomy (synthetic) | none | HIGH | Reviewer → General Counsel |
| REQ-1005 | Series B financing: term sheet (synthetic) | >1m | HIGH | Reviewer → Legal Ops Lead → General Counsel → Board note |
| REQ-1006 | Vendor security questionnaire: analytics tool (synthetic) | 50k-250k | MEDIUM | Reviewer → Legal Ops Lead |
| REQ-1007 | Customer dispute: SLA credits claim (synthetic) | 250k-1m | HIGH | Reviewer → Legal Ops Lead → General Counsel |
| REQ-1008 | Employment offer: senior engineer (synthetic) | none | MEDIUM | Reviewer |
