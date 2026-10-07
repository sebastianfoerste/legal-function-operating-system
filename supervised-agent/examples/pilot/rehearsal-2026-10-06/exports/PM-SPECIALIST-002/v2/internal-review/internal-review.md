# Internal review export: Enterprise SaaS MSA deviation review (synthetic)

> INTERNAL REVIEW DRAFT. Not approved. Not a delivery package. Do not pass on outside the review team.
> Matter PM-SPECIALIST-002, version 2, state review
> Requester: Synthetic Requester A, Revenue Operations
> Generated (UTC): 2026-10-06T19:22:37.773377Z

## 1. Executive summary

The customer draft "synthetic-msa-specialist.docx" from Example Retail SE (fictitious) was reviewed against synthetic:saas-msa-deviation-playbook@v1. 7 deviation(s) from the playbook were found. Reverted to the standard position: 0. Settled on fallback wording: 0. Accepted as an exception: 0. 7 are still open.

The parent operating system rates the matter MEDIUM risk, priority P2_high, queue Commercial. The approval tier it requires is General Counsel. No final approval is recorded for this version.

2 obligation(s) remain open and each has an owner and a deadline below. Signature target date: 2026-09-30.

## 2. Issue and deviation list

| Clause | Topic | Severity | Counterparty wording | Outcome | Final wording | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| clause 2.1 | Payment terms | low | ninety (90) days | Not yet decided | thirty (30) days | The draft extends the payment period beyond the standard thirty days. |
| clause 3.1 | Audit right | medium | at any time and without prior notice | Not yet decided | once in any twelve (12) month period on thirty (30) days' prior written notice, during business hours and subject to Supplier's confidentiality requirements | The draft grants an unrestricted audit right without notice or frequency limit. |
| clause 4.1 | Subprocessors | high | Supplier shall not engage any subprocessor for the processing of Customer Personal Data. | Not yet decided | Supplier may engage the subprocessors listed in Annex 2 and shall give Customer thirty (30) days' prior notice of any intended addition or replacement, during which Customer may object on reasonable grounds. | The draft prohibits every subprocessor, which the service architecture cannot meet. |
| clause 5.1 | Limitation of liability | high | three hundred percent (300%) | Not yet decided | one hundred percent (100%) | The draft raises the aggregate liability cap above the standard position. |
| after clause 5.1 | Exclusion of indirect loss | medium | (no clause in the draft) | Not yet decided | Neither party is liable for indirect or consequential loss, loss of profit or loss of data, except where liability cannot be limited or excluded by law. | The draft contains no exclusion of indirect or consequential loss. |
| clause 6.1 | Roadmap commitment | high | Supplier shall deliver the features described in the Product Roadmap no later than 31 December 2026. | Not yet decided | Any product roadmap is provided for information only and is not a commitment to deliver any feature or functionality. | The draft converts the product roadmap into a dated delivery obligation. |
| clause 6.2 | Most-favoured-customer pricing | medium | 6.2	Customer shall be entitled to the most favourable pricing offered by Supplier to any other customer. | Not yet decided | (clause deleted) | The draft adds a most-favoured-customer pricing clause. |

## 3. Reviewed document

draft-redline.docx carries every proposed change as a tracked change against the unmodified customer draft (SHA-256 7a170f9dc8f467e08e6406a4b7c935ba0ee8626daec45e43159a4f696c6c3973). Rejecting all tracked changes in Word restores the customer draft exactly.

## 4. Accepted exceptions

No exception to the playbook was accepted.

## 5. Outstanding obligations

| Obligation | Arises from | Owner | Deadline |
| --- | --- | --- | --- |
| Record and track the customer commitment: higher liability cap | Intake commitment register | Commercial Counsel: Synthetic Matter Owner B (Commercial Counsel) (syn-owner-legalops) | 2026-09-30 |
| Record and track the customer commitment: controlled annual audit right | Intake commitment register | Commercial Counsel: Synthetic Matter Owner B (Commercial Counsel) (syn-owner-legalops) | 2026-09-30 |

## 6. Approval record

No approval is recorded for this version.

- Matter version: 2
- Content hash: 19f155d9442ffc856778ca487b46dd68eab42ad691259dd34693c7e22f1ed7aa
- Reviewed-state hash: d6b9f63e2de64d55206166c1dfb3e8f7d91084b970f49b9b0e3122bfb9667b26
- Event chain root: 0e7e9c4586aa295bf461b399030c2c306a461ba782dd8143c115f8c6cc32cc76
- Approvers are simulated local roles, not authenticated identities.

| Export check | Result | Detail |
| --- | --- | --- |
| assessment_present | pass | assessment loa_cd832438807ca3b3 |
| assessment_bound_to_version | pass | assessment is bound to version 2 |
| assessment_approved | fail | parent assessment is needs_review and not approved for export |
| source_boundary_clear | pass | no blocked source prefix |
| no_blocker_findings | pass | no blocker finding |
| document_hash_matches | pass | document digest matches the reviewed version |
| changes_decided | fail | export requires every proposed change to be decided; undecided: chg-audit-right-7e46718e, chg-liability-cap-c8bcf70e, chg-liability-exclusions-c8bcf70e, chg-most-favoured-customer-e9bbead5, chg-payment-terms-2816324e, chg-roadmap-commitment-632261c0, chg-subprocessors-3340f2a6 |
| no_unresolved_blockers | fail | unresolved: coverage_gap cov-e01bae58265f on source_span coverage:e01bae58265f (current) |
| required_reviewer_decisions | fail | specialist_signoff:Privacy Counsel is missing; final_approval:General Counsel is missing |
| audit_chain_verified | pass | audit chain intact |
| matter_state_permits_delivery | fail | matter state review does not permit delivery |

## Verification performed and remaining human review

Three different things were checked for each change. The allowlist check only establishes that a reference uses a permitted source prefix. The quote check establishes that the quoted wording is present at the stated place in the stated source version. Whether the source supports the wording for this matter was confirmed by a reviewer, not by software.

| Change | Allowlist check | Quote check | Human confirmation |
| --- | --- | --- | --- |
| chg-payment-terms-2816324e | synthetic:saas-msa-deviation-playbook@v1#payment-terms: pass; synthetic:matter-document:7a170f9dc8f4#para:5: pass | quote_found; quote_found | pending |
| chg-audit-right-7e46718e | synthetic:saas-msa-deviation-playbook@v1#audit-right: pass; synthetic:matter-document:7a170f9dc8f4#para:7: pass | quote_found; quote_found | pending |
| chg-subprocessors-3340f2a6 | synthetic:saas-msa-deviation-playbook@v1#subprocessors: pass; synthetic:matter-document:7a170f9dc8f4#para:9: pass | quote_found; quote_found | pending |
| chg-liability-cap-c8bcf70e | synthetic:saas-msa-deviation-playbook@v1#liability-cap: pass; synthetic:matter-document:7a170f9dc8f4#para:11: pass | quote_found; quote_found | pending |
| chg-liability-exclusions-c8bcf70e | synthetic:saas-msa-deviation-playbook@v1#liability-exclusions: pass; synthetic:matter-document:7a170f9dc8f4#para:11: pass | quote_found; quote_found | pending |
| chg-roadmap-commitment-632261c0 | synthetic:saas-msa-deviation-playbook@v1#roadmap-commitment: pass; synthetic:matter-document:7a170f9dc8f4#para:13: pass | quote_found; quote_found | pending |
| chg-most-favoured-customer-e9bbead5 | synthetic:saas-msa-deviation-playbook@v1#most-favoured-customer: pass; synthetic:matter-document:7a170f9dc8f4#para:14: pass | quote_found; quote_found | pending |
