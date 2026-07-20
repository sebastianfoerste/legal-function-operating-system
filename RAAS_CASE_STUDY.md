# Case study: industrial robotics RaaS deal desk

## The management question

A cross-border robotics agreement combines hardware, installation, fleet software,
AI-enabled vision and path planning, remote support, product data, service levels,
and a multi-year recurring commercial model.

The General Counsel must answer four questions quickly:

1. Can the company sign the current draft?
2. Which contract positions exceed the approved playbook?
3. Who must approve the open points?
4. What could delay deployment, revenue, or regulatory readiness?

This case study encodes that decision process as deterministic, reviewable rules over
one synthetic Germany-US transaction.

## Synthetic scenario

The provider offers a 36-month Robotics-as-a-Service framework with an initial
deployment in Augsburg and a later rollout in Austin. The provider retains robot
title. The package includes site integration, fleet-management software, AI vision,
path planning, remote monitoring, maintenance, support, and software updates.

The customer draft requests:

- broad uncapped liability;
- subjective acceptance;
- ownership of all site-specific improvements;
- unrestricted use of all product data for model training;
- an unsigned site-safety responsibility allocation;
- uncapped service credits;
- termination for convenience without recovery of deployment costs;
- broad global industry exclusivity; and
- Texas law for the global framework.

Every name and fact is synthetic.

## Deterministic outputs

`make demo` produces five RaaS artifacts:

1. [`examples/raas-deal-pack.md`](examples/raas-deal-pack.md), the human-readable decision pack.
2. [`examples/raas-deal-pack.json`](examples/raas-deal-pack.json), the typed machine-readable result.
3. [`examples/raas-deal-room.html`](examples/raas-deal-room.html), an offline local reviewer cockpit.
4. [`examples/raas-deal-desk.svg`](examples/raas-deal-desk.svg), the generated visual proof surface.
5. [`examples/raas-source-manifest.json`](examples/raas-source-manifest.json), the dated primary-source manifest.

The current synthetic draft is blocked. The pack records the blocking clauses, the
approvers, Finance questions, regulatory evidence, external-counsel scopes, and a
founding General Counsel 100-day plan.

## Legal and commercial judgment encoded

The negotiation layer addresses the recurring interfaces in a RaaS transaction:

- hardware ownership, custody, insurance, and removal;
- objective acceptance and commissioning;
- uptime measurement and service credits;
- liability proportionality;
- platform and improvement IP;
- telemetry, connected-product data, and model improvement;
- remote access and cybersecurity response;
- product and site-safety responsibility;
- term, termination, and deployment-cost recovery;
- expansion options and change control; and
- cross-border governing law and entity allocation.

Each rule exposes:

- the requested position;
- the illustrative standard position;
- a fallback;
- the escalation trigger;
- the required approvers;
- the rationale; and
- the precise synthetic input field used as evidence.

## Finance handoff

The pack makes no accounting conclusion. It gives Finance a structured question set
covering:

- performance obligations;
- acceptance and transfer of control;
- variable consideration and service credits;
- enforceable contract term;
- lease assessment;
- options and modifications;
- side commitments; and
- the Germany-US contracting and intercompany model.

The questions identify IFRS 15, ASC 606, IFRS 16, and ASC 842 as the relevant review
frameworks. Finance remains the accountable decision-maker.

## Regulatory readiness

The matrix identifies the actor, issue, gate effect, owner, required evidence,
timing, legal effect, and primary source for:

- the current EU machinery framework;
- the Machinery Regulation transition;
- the Artificial Intelligence Act;
- the Data Act;
- the Cyber Resilience Act;
- the revised Product Liability Directive; and
- GDPR and international transfers.

The source snapshot is dated and hashed. It distinguishes directly applicable
regulations from directives requiring national implementation. Application and
classification still depend on verified product facts and the law current at the
actual review date.

## Controls and limits

- Synthetic data only.
- Deterministic, offline, standard-library execution.
- No automated contract drafting.
- No legal or accounting conclusion presented as final.
- No external communication or instruction of counsel.
- Named human review required for every consequential position.
- Primary sources recorded with a verification date and digest.

## Validation

```bash
make test
make demo
make check
```

The test suite covers the signing gate, non-starters, evidence references, Finance
handoff, regulatory sources, counsel scopes, 100-day plan, deterministic rendering,
CLI gating, and output generation.
