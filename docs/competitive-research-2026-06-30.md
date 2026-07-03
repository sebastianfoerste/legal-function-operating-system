# Competitive Research: Legal AI And Contract Review Stores

Date: 2026-06-30

Purpose: identify the crowded feature surface around legal AI apps, contract review, and legal operations tooling, then choose the strongest public proof feature for this repo.

## Search Surfaces

- GitHub repository search for `legal AI agent`, `contract review AI`, and `legal ops`.
- Apple App Store official iTunes Search API for `legal AI` and `contract review`.
- Google Play public search pages for `legal AI` and `contract review`.
- Chrome Web Store, Google Workspace Marketplace, and Slack Marketplace public searches for `legal AI`.
- Microsoft AppSource and Amazon Appstore were attempted from the CLI. Both blocked automated access during this pass, so they are treated as coverage boundaries rather than inspected result sets.

## GitHub Signals

- `Paparusi/legal-ai-agent`: high-star legal AI agent result, active near the research date.
- `sure-scale/doc-haus`: local-document legal AI agent with Word redline positioning.
- `NEU-ZHA/legal-ai-skills`: legal AI skills for citation and DOCX workflows.
- `anylegal-ai/anylegal-oss`: open-source legal AI agent harness.
- `xiaodingfeng/contract-review-v2`: contract upload, AI pre-analysis, OnlyOffice preview, knowledge retrieval, Q&A, and controlled web search.
- Contract-review searches also returned many small demos focused on clause extraction, risk scoring, upload flows, Gemini-based review, and MCP-style contract review.

The GitHub market is deepest around agent harnesses, redlining, legal research helpers, and contract-review demos. Legal operations control evidence is comparatively sparse.

## App Store Signals

Apple App Store results include consumer and small-business legal tools such as Legal AI Assistant, AI Legal Documents Generator, Rocket Lawyer, Vikk, Lexis+ with Protege Mobile, AI Lawyer, Contract Genius, ClauseLens, Contract Assistant, BeforeSend, BeforeYouSign, Sign Wise, Simply, Contract AI, and CounselVault.

Google Play public search showed similar clusters: AI lawyer apps, Rocket Lawyer, LegalAI-style explainers, ClauseLens, ContractEasy, Contractly, and AI contract analyzers.

The mobile market is crowded around consumer legal Q&A, document generation, contract explanation, and lightweight contract review.

## Marketplace Signals

Chrome Web Store and Google Workspace Marketplace results emphasize legal simplification, privacy-policy analysis, redlining, document review, legal Q&A, and hallucination-watch style browser utilities.

Slack Marketplace surfaced legal assistant and legal hold style entries. That signal is more workflow integration than evidence design.

The enterprise-adjacent stores favor document workflows, browser or workspace convenience, and collaboration add-ons. They give less reviewer-facing proof of source boundaries, approval gates, disabled external actions, and artifact integrity.

## Product Implication

The strongest public proof feature for `legal-ops-agent` is a Trust Cockpit:

- One reviewer-facing output that shows status, review state, export gate, source boundary, external-action block, commitments, owners, SLA, and artifact digests.
- JSON and Markdown outputs generated through the canonical CLI path.
- A controlled MCP tool for the same evidence surface.
- A dated committed snapshot using the synthetic SaaS MSA deviation fixture.

This positions the repo around operational trust and legal workflow control, where the competitive field is thinner than consumer chat, document generation, redlining, or generic contract analysis.

## Source Links

- GitHub legal AI agent search: <https://github.com/search?q=legal+AI+agent&type=repositories>
- GitHub contract review AI search: <https://github.com/search?q=contract+review+AI&type=repositories>
- GitHub legal ops search: <https://github.com/search?q=legal+ops&type=repositories>
- Apple App Store legal AI API: <https://itunes.apple.com/search?term=legal%20AI&country=us&entity=software&limit=20>
- Apple App Store contract review API: <https://itunes.apple.com/search?term=contract%20review&country=us&entity=software&limit=20>
- Google Play legal AI search: <https://play.google.com/store/search?q=legal%20AI&c=apps&hl=en_US&gl=US>
- Google Play contract review search: <https://play.google.com/store/search?q=contract%20review&c=apps&hl=en_US&gl=US>
- Chrome Web Store legal AI search: <https://chromewebstore.google.com/search/legal%20AI>
- Google Workspace Marketplace legal AI search: <https://workspace.google.com/marketplace/search/legal%20AI>
- Slack Marketplace legal AI search: <https://slack.com/marketplace/search?q=legal%20ai>
- Microsoft AppSource legal AI search attempted: <https://appsource.microsoft.com/en-us/marketplace/apps?search=legal%20AI&page=1>
- Amazon Appstore legal AI search attempted: <https://www.amazon.com/s?k=legal+AI&i=mobile-apps>

## Round 2: Audit Integrity Chain

Date: 2026-06-30

Purpose: check whether tamper-evident or hash-chained audit trails are a contested
space before committing to it as the round-2 differentiator.

### Search Surfaces

- GitHub repository search for `tamper-evident audit log legal`, `hash chain audit
  trail compliance`, and `verifiable audit trail SaaS legal tech`.
- Apple App Store and Google Play searches for `audit trail compliance`.
- Chrome Web Store and Google Workspace Marketplace searches for `tamper evident
  audit` / `audit trail`. Slack Marketplace search attempted.
- Retried Microsoft AppSource and Amazon Appstore (both blocked automated access in
  round 1) with the same `audit trail` query.

### GitHub Signals

The hash-chain technique itself is not white space. Several active projects implement
exactly this pattern, some closer to this repo's shape than expected:

- `AiAgentKarl/agent-audit-trail-mcp`: immutable audit logging for AI agents — a
  hash-chained event log exposed as an MCP tool, with integrity verification and an
  EU AI Act compliance framing. Closest mechanical match found: hash chain plus MCP
  surface, same as this repo's `legal.audit.verify`.
- `Ashish-Barmaiya/attest`: multi-tenant, append-only audit logging service with
  cryptographic proof that history has not been silently rewritten.
- `AyoubTadlaoui/GoLogX`: Go hash-chained, optionally Ed25519-signed audit log
  handler with offline chain verification, zero third-party dependencies.
- `AuditKitDev/auditkit`: open-source, tamper-evident audit logging for B2B SaaS.
- `Jreamr/ai-action-ledger` and `Constellation-Labs/gate-oc-audit`: tamper-evident
  audit logs scoped to AI agent or AI coding agent actions specifically.
- `Justin0504/Aegis`: runtime policy enforcement for AI agents combining a
  cryptographic audit trail with human-in-the-loop approvals and a kill switch — the
  closest conceptual match to this repo's approval-gate-plus-audit-chain pairing,
  though scoped to general agent tool calls, not legal matters.
- `grcorsair/corsair`: signs compliance findings as W3C Verifiable Credentials
  (Ed25519, JWT-checkable) rather than a hash chain — a different cryptographic
  approach to the same "don't just trust the PDF" problem.

None of these combine the mechanism with a typed legal-matter intake, deterministic
risk triage, reviewer routing, or an export gate that the chain itself blocks. They
are general-purpose agent/SaaS audit-logging infrastructure, not legal-ops workflow
tools.

### App Store And Marketplace Signals

- Apple App Store and Google Play results for `audit trail compliance` returned
  physical-world inspection apps almost exclusively: Site Audit Pro, EASE Audits,
  Nimonik, Contractor Compliance, KPA Vera Suite, GoAudits, Enablon Audit, and
  similar site/safety/facility inspection tools. Google Play results also picked up
  unrelated hiking-trail apps on the word "trail." Zero legal AI or cryptographic
  audit-log results on either store.
- Chrome Web Store results for `tamper evident audit` surfaced GetProofAnchor and
  ProofSnap — extensions that capture a web page as court-admissible evidence (SHA-256
  hash, digital signature, blockchain timestamp). Closer in spirit than the mobile
  stores, but these evidence the *content of a captured page*, not an internal legal
  workflow's audit trail.
- Google Workspace Marketplace results for `audit trail` were e-signature and
  SOX-control-documentation tools (Docusign, SignRequest, Tickmark Pro) — none
  hash-chain the audit trail itself.
- Slack Marketplace search returned a client-rendered page with no results in the
  static fetch; inconclusive, not a finding either way.
- Microsoft AppSource: still blocked (HTTP 403), same as round 1.
- Amazon Appstore: still blocked (HTTP 503), same as round 1.

### Product Implication

The honest finding is narrower than "nobody does this." Hash-chained, tamper-evident
audit logging is an established pattern with active GitHub implementations, including
at least one (`agent-audit-trail-mcp`) that pairs it with an MCP tool the way this
repo does. The differentiation is not the cryptographic technique — it is combining
that technique with a legal-matter review workflow: typed intake, deterministic risk
triage, reviewer routing, and an export gate that the chain itself can block, all
surfaced together in one reviewer-facing Trust Cockpit. No project found across
GitHub, the app stores, or the marketplaces checked combines those two things. The
app-store and marketplace surfaces specifically remain uncontested for hash-chain
audit tooling of any kind — they are dominated by physical inspection and e-signature
products instead.

### Source Links

- GitHub tamper-evident audit log search: <https://github.com/search?q=tamper-evident+audit+log+legal&type=repositories>
- GitHub hash chain audit trail search: <https://github.com/search?q=hash+chain+audit+trail+compliance&type=repositories>
- GitHub verifiable audit trail search: <https://github.com/search?q=verifiable+audit+trail+SaaS+legal+tech&type=repositories>
- Apple App Store audit trail API: <https://itunes.apple.com/search?term=audit%20trail%20compliance&country=us&entity=software&limit=20>
- Google Play audit trail search: <https://play.google.com/store/search?q=audit%20trail%20compliance&c=apps&hl=en_US&gl=US>
- Chrome Web Store tamper-evident audit search: <https://chromewebstore.google.com/search/tamper%20evident%20audit>
- Google Workspace Marketplace audit trail search: <https://workspace.google.com/marketplace/search/audit%20trail>
- Slack Marketplace audit trail search: <https://slack.com/marketplace/search?q=audit%20trail>
- Microsoft AppSource audit trail search attempted: <https://appsource.microsoft.com/en-us/marketplace/apps?search=audit%20trail&page=1>
- Amazon Appstore audit trail search attempted: <https://www.amazon.com/s?k=audit+trail+compliance&i=mobile-apps>
- `agent-audit-trail-mcp`: <https://github.com/AiAgentKarl/agent-audit-trail-mcp>
- `attest`: <https://github.com/Ashish-Barmaiya/attest>
- `GoLogX`: <https://github.com/AyoubTadlaoui/GoLogX>
- `auditkit`: <https://github.com/AuditKitDev/auditkit>
- `ai-action-ledger`: <https://github.com/Jreamr/ai-action-ledger>
- `gate-oc-audit`: <https://github.com/Constellation-Labs/gate-oc-audit>
- `Aegis`: <https://github.com/Justin0504/Aegis>
- `corsair`: <https://github.com/grcorsair/corsair>
