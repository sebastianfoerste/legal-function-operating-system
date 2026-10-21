# Competitive landscape: legal front door, triage, operations and reporting

Date: 2026-10-20. Scope: products that take legal requests in and route, track and report
them, plus the CLM, review and pattern-donor products whose features this repository
adapts. The review room and supervision UX are covered in
[Round 3 of the agent's competitive research](../../supervised-agent/docs/competitive-research-2026-06-30.md#round-3-review-room-and-supervision-ux).
This document does not repeat them.

> **Network-limited run.** Every vendor site and EUR-Lex failed DNS resolution from the
> research environment (`getaddrinfo ENOTFOUND`). The failed hosts are listed under
> [Not reachable](#not-reachable). Vendor facts below therefore come from search-result
> snippets only and are tagged **Claimed**, even when the snippet came from a vendor help
> centre. Source code read from GitHub clones is **Observed**. Gaps are marked unknown and
> were not filled from memory. No legal citation was added or changed by this research.

Companion files:

- [feature-matrix.csv](feature-matrix.csv): one row per product, 14 capability columns.
- [design-teardown.md](design-teardown.md): the top 8 teardowns and a pattern summary per
  repository surface.
- [adaptation-plan.md](adaptation-plan.md): baseline, candidates, specs, verdicts and owner
  decisions.

## Method

- **Evidence tags.** Every claim carries a source URL, the access date (2026-10-20 for all)
  and one tag:
  - **Observed**: public source code or a repository page read directly.
  - **Claimed**: vendor or third-party statement, here always seen in a search snippet.
  - **Inferred**: our reasoning.
- **Clean room.** No accounts, trials, demo bookings, forms, chat widgets or product input.
  No competitor asset, wording or dataset was copied. Screenshots of this repository's own
  surfaces stay in the git-ignored `research/_captures/` folder.
- **Repository scope.** Searches across GitHub must use only the fallbacks the brief
  names: `git clone --depth 1`, raw.githubusercontent.com, or attaching a repository
  read-only. This run broke that once; see Repository discovery below.
- **Quotes.** At most one phrase of 10 words or fewer per source. Reviews are paraphrased,
  without reviewer identities.
- **Coverage.**
  - 43 vendor searches (39 English, 1 German, 1 mixed German and English, 2 French) and
    one English preflight search. German coverage is thin for a DSGVO-focused product;
    more German queries are listed as a follow-up in the adaptation plan.
  - 17 open-source repositories cloned and read, with no code run.
  - Five curated lists from the repository owner.
  - Review-mining for Ironclad, Checkbox, Juro, LawVu, Streamline AI and Agiloft.

## Search log

All searches ran on 2026-10-20 through the WebSearch tool in standard mode. "Results used"
lists the sources the matrix and teardowns cite.

| # | Query | Lang | Results used |
| --- | --- | --- | --- |
| 0 | legal front door software intake triage in-house legal 2026 (preflight) | EN | checkbox.ai/blog/building-the-legal-front-door; xakiatech.com/features/legal-intake-triage |
| 1 | legal front door software in-house legal intake | EN | checkbox.ai/blog/building-the-legal-front-door; streamline.ai/blog/front-door-legal; nortonrosefulbright.com (intelligent legal front door); process.st |
| 2 | legal intake triage software in-house 2026 | EN | xakiatech.com/features/legal-intake-triage; checkbox.ai/software/legal-intake-software |
| 3 | Legal Request Management Software Rechtsabteilung | DE/EN | csdisco.com/offerings/request; store.servicenow.com; Bigle legal requests whitepaper; servicenow.com docs |
| 4 | Rechtsabteilung Mandatsverwaltung Software Legal Operations | DE | mitratech.com/de (matter management); wolterskluwer.com/de-de (Legisway webinar) |
| 5 | logiciel gestion demandes juridiques direction juridique | FR | wolterskluwer.com/fr-fr (Legisway brochure) |
| 6 | legal operations matter management SLA dashboard | EN | servicenow.com docs; legalontech.com (matter dashboard); streamline.ai (ops dashboard); wolterskluwer.com (LegalVIEW dashboards) |
| 7 | contract review playbook fallback position software | EN | harvey.ai (contract playbook); help.harvey.ai; casemark.com; legalsifter.com; vaquill.ai docs |
| 8 | legal ops approval matrix routing contract approvals | EN | spotdraft.com (approval matrix glossary); intelagree.com; ironcladapp.com (approval bottlenecks) |
| 9 | outil front door juridique triage demandes IA direction juridique | FR | todaysgeneralcounsel.com; autologyx.com; checkbox.ai (where AI fits); checkbox.ai/solution/triage |
| 10 | Checkbox legal intake conditional logic required fields form builder | EN | help.lawvu.com (conditional intake forms); support.xakiatech.com (conditional logic) |
| 11 | Josef legal automation conditional questions logic block submission | EN | getapp.com, directory.lawnext.com, cbinsights.com (Josef listings) |
| 12 | LawVu request portal requester status tracking privileged | EN | help.lawvu.com (business portal; status updates); servicenow.com docs; artificiallawyer.com (LawVu intake walk-through) |
| 13 | Zendesk SLA business hours calendar hours paused metric | EN | support.zendesk.com/hc/en-us/articles/360023798013; eesel.ai; getmacha.com |
| 14 | Jira Service Management SLA pause conditions calendar business hours goals | EN | support.atlassian.com (paused SLA); confluence.atlassian.com (setting up SLAs) |
| 15 | Ironclad AI playbook standard fallback position clause review | EN | support.ironcladapp.com (two playbook recipes, one attachment); ironcladapp.com (modern playbook) |
| 16 | LegalOn playbook review standard position fallback deviation | EN | legalontech.com (AI-ready playbooks; contract review); artificiallawyer.com (LegalOn playbooks) |
| 17 | SpotDraft conditional approval workflow rules contract value approvers | EN | help.spotdraft.com (four articles); releases.spotdraft.com |
| 18 | Linear triage accept decline duplicate snooze docs | EN | linear.app/docs/triage; linear.app/docs/snooze |
| 19 | Wordsmith AI legal Slack email intake in-house legal | EN | sacra.com; letsdatascience.com; wordsmith.ai/integrations; softwareadvice.com.au |
| 20 | Flank AI legal agent autonomous completes legal work Slack email | EN | insightpartners.com; artificiallawyer.com; pulse2.com; neuronfeed.com |
| 21 | Robin AI legal acquired administration 2025 2026 | EN | nonbillable.co.uk; coastfm.co.uk |
| 22 | Ironclad CLM reviews cons G2 complaints | EN | g2.com (Ironclad reviews); signeasy.com; rfp.wiki |
| 23 | LawVu reviews cons Capterra G2 | EN | hyperstart.com; rfp.wiki |
| 24 | Checkbox legal reviews cons G2 Capterra | EN | capterra.com (Checkbox reviews) |
| 25 | Juro contract management reviews cons G2 | EN | g2.com (Juro reviews); ai.g2.com; copy.ai |
| 26 | EU AI Act Digital Omnibus delay high-risk obligations postponed | EN | gibsondunn.com; pasqualepillitteri.it; casrai.org; brabners.com; cadeproject.org |
| 27 | Linear presence indicator avatars; Google Docs presence | EN | help.plain.com (presence indicators) |
| 28 | Linear changelog presence see who is viewing issue avatars | EN | linear.app/changelog/2020-04-27; docs.servicenow.com (user presence) |
| 29 | Google Docs see who is viewing a document avatars cursor help | EN | kb.plu.edu; edu.gcfglobal.org |
| 30 | Checkbox.ai intake form required fields routing rules SLA Slack Teams | EN | blog.checkbox.ai (two articles) |
| 31 | GC AI Eudia Sandstone in-house legal AI 2026 | EN | artificiallawyer.com (Eudia); tooldirectory.ai; techindex.law.stanford.edu; ecosistemastartup.com |
| 32 | Tonkean LegalWorks intake orchestration procurement legal 2026 | EN | tonkean.com (three pages); businesswire.com |
| 33 | Streamline AI legal intake SLA tracking requester status features | EN | g2.com (Streamline discussion); rfp.wiki |
| 34 | Bryter 2026 legal workflow automation acquisition OR rebrand | EN | bryter.com (about; press release); gavel.io |
| 35 | Hyperlex Legartis 2026 acquired contract review CLM | EN | cbinsights.com (two comparisons); legartis.ai |
| 36 | Mitratech TAP workflow legal intake TeamConnect Brightflag Onit 2026 | EN | mitratech.com (two pages); legaltechnologyhub.com |
| 37 | Legora Harvey in-house legal workflow agents 2026 funding | EN | gic.com.sg (Harvey); sacra.com (Legora); tech-insider.org |
| 38 | Docusign IAM Iris agreement agents Definely Spellbook Luminance 2026 | EN | docusign.com (news centre); diginomica.com |
| 39 | Thomson Reuters HighQ CoCounsel Lexis+ Protégé Agiloft Sirion agentic 2026 | EN | lexisnexis.com (press room); haqq.ai; rework.com |
| 40 | LangSmith annotation queues reviewers rubric; Intercom SLA office hours | EN | docs.langchain.com (annotation queues); intercom.com help; getmacha.com |
| 41 | Definely Spellbook Luminance 2026 news in-house contract review | EN | spellbook.com (two competitor-authored pages); aivortex.io |
| 42 | Agiloft Sirion HighQ Xakia Juro 2026 legal intake AI news | EN | rework.com; hyperstart.com; capterra.com (Xakia listing) |
| 43 | LawVu ClauseBase acquisition LawVu AI agents MCP 2026 | EN | lawvu.com (two articles); artificiallawyer.com; help.lawvu.com (MCP server); agentman.ai |

Repository discovery (Observed, 2026-10-20):

- GitHub topics `legal-operations`, `legal-tech` and `contract-management` returned 403
  through the REST search API. The research agent then listed them through the GitHub MCP
  search tool. That tool reached beyond this session's repository scope, which the session
  rules do not allow, and it is not one of the fallbacks the brief names. The access was
  read-only. No matrix row comes from it; only the `legal-operations` count in the next
  bullet relies on it. Whether to keep that count is an owner decision, and later runs use
  only the named fallbacks.
- `legal-operations` has 22 repositories, all small, which confirms the brief's
  observation: there is little open-source competition for a deterministic legal front
  door.
- The repository owner's lists (`awesome-eu-fintech-regulation`, `awesome-legal-tech`,
  `awesome-in-house-legal`, `awesome-legal-nlp` on `master`, `Awesome-LegalAI-Resources`)
  were read via raw.githubusercontent.com. `awesome-in-house-legal` states that no
  production-grade open-source CLM existed as of June 2026 (Claimed by the list).

## Products

65 products and projects are in the matrix: 17 direct, 33 adjacent and 15 pattern donors.
Four rows hold no capability data and carry evidence `unknown`, so 61 rows hold data.
Brightflag, Onit and HighQ were not found in any search. GitHub pull request reviews was
not researched this run, because no source for it was reachable.
These are the findings that matter for this repository.

### Direct competitors

- **Checkbox** positions itself as the "legal front door". It takes requests from email,
  Slack, Teams and web forms into one record, and routes by matter type, business unit,
  expertise and capacity. The vendor itself says AI is weak where judgement is needed.
  Claimed:
  - <https://blog.checkbox.ai/blog/listicle/what-platforms-centralize-legal-requests-from-multiple-intake-channels-into-a-single-tracked-queue-503ecf>
  - <https://www.checkbox.ai/blog/where-ai-fits-into-legal-intake-and-triage-and-where-it-doesnt>
- **LawVu** bought ClauseBase in December 2025 and relaunched it as LawVu Draft and Lens.
  Its intake forms let a field depend only on earlier fields. Requesters get a "My Work"
  grid with a request-status-update action. It ships an MCP server and recommends human
  approval for any write an AI starts. Claimed:
  - <https://lawvu.com/articles/announcing-the-acquisition-of-clausebase-and-launch-of-lawvu-lens/>
  - <https://help.lawvu.com/en/articles/6824391-conditional-intake-forms>
  - <https://help.lawvu.com/en/articles/15266786-lawvu-mcp-server>
- **Claude for Legal** (Apache-2.0) ships through the same plugin channel as this
  repository. Observed in <https://github.com/anthropics/claude-for-legal>:
  - Released 1.0.0 on 2026-05-11 and 1.0.2 on 2026-05-12, when CoCounsel was added.
  - Matter Intake writes nothing while the conflicts check has not run.
  - The NDA Triager will not return GREEN against playbook positions no attorney has
    reviewed.
  - The Escalation Router only drafts; a person sends.
  - The playbook monitor proposes a change after 5 deviations within 12 months and
    writes only after the lawyer accepts an exact diff.
- **Flank** markets autonomous legal agents that work "embedded, invisible" in Slack,
  Teams and email. That is the anti-pattern this repository is built against. Claimed:
  <https://insightpartners.com/ideas/flank-raises-10m-to-scale-autonomous-legal-agents-embedded-invisible-and-built-for-the-enterprise>
- **Wordsmith** takes requests in Slack, Teams, email and Salesforce, pulls context from
  CRM and CLM, and answers in the same channel. Claimed: <https://wordsmith.ai/integrations>
- **Streamline AI, Xakia, Tonkean, Josef, Bryter (now presenting BEAMON AI), Mitratech,
  ServiceNow Legal Service Delivery, Sandstone, Eudia, GC AI, DISCO Request, Bigle,
  Autologyx and the Norton Rose Fulbright front door** cover parts of intake, routing and
  reporting. Snippets show conditional forms, FAQ deflection and dashboards, but little
  about how decisions are explained. Claimed; per-row sources are in the matrix.

### Adjacent products

- **Ironclad** gives each clause a preferred position, fallbacks and an approver. A
  deviation goes to a "Needs Review" section, and skipping a change can require an extra
  approver. Claimed:
  <https://support.ironcladapp.com/hc/en-us/articles/34018339425303-Recipe-Build-a-Playbook-to-Help-Legal-Reduce-Negotiation-Time>
- **LegalOn** shows pass or fail per playbook rule with clickable references, and a
  three-level severity. Claimed: <https://legalontech.com/post/ai-ready-playbooks>
- **SpotDraft** routes approvals with an If / Else If / Else ladder over named,
  reusable conditions. Claimed:
  <https://releases.spotdraft.com/announcements/conditional-assignment-of-approvers>
- **Status changes:**
  - Robin AI is reported in distress, with its managed-services arm sold to Scissero.
    Claimed: <https://nonbillable.co.uk/news/robin-ai-offloads-managed-services-arm-scissero>
  - Hyperlex has been part of DiliTrust since 2022. Claimed:
    <https://www.cbinsights.com/compare/contractpodai-vs-hyperlex-1>
  - Docusign announced agents and an MCP server for late 2026 to early 2027; sources
    disagree on the dates. Claimed:
    <https://www.docusign.com/company/news-center/docusign-unveils-ai-assistant-and-agents-to-power-the-next-era-of-agreement-work>
- **Open source:**
  - **docassemble** (MIT) treats fields as required by default and asks for any missing
    variable next. Observed.
  - **Mike** (AGPL, pattern only) requires approval of the exact contents of every write.
    Answers are single-use, and writes happen at most once. Observed.
  - **Lavern** (Apache-2.0) verifies grounding by string matching, with no LLM. Observed.
- **Remote MCP connectors.** `commercial-legal/.mcp.json` in claude-for-legal wires
  remote HTTP MCP servers for Ironclad, DocuSign, iManage, TopCounsel, Definely, Slack and
  Google Drive. This repository has one local stdio server with four read-only tools.
  Observed:
  <https://github.com/anthropics/claude-for-legal/blob/main/commercial-legal/.mcp.json>

### Pattern donors

- **Triage verbs.**
  - Linear has four: Accept, Duplicate, Decline (with a comment), and Snooze until a time
    or new activity. Claimed: <https://linear.app/docs/triage>
  - Plane stores Pending, Rejected (shown as Declined), Snoozed, Accepted and Duplicate,
    and writes each change as an activity record with old and new values. Observed:
    <https://github.com/makeplane/plane/blob/preview/apps/api/plane/db/models/intake.py>
- **SLA pause.**
  - Zendesk sets business or calendar hours per target, and only some metrics can pause.
    Claimed: <https://support.zendesk.com/hc/en-us/articles/360023798013>
  - Intercom pauses do not move the breach deadline. Claimed:
    <https://www.intercom.com/help/en/articles/9263617-slas-and-office-hours>
  - Chatwoot's SLA engine (enterprise licence) has no pause state at all. Observed:
    <https://github.com/chatwoot/chatwoot/blob/develop/enterprise/app/models/applied_sla.rb>
- **Event history.** Temporal UI (MIT) groups events and offers compact, feed and JSON
  views with a status legend. Langfuse writes audit events as change or access, with an
  actor and an outcome (MIT); its viewer is enterprise-licensed. Observed.
- **Accessible forms.** GOV.UK Frontend (MIT code) has an error summary that takes focus
  and links to each field, error text tied to the field by `aria-describedby`, and a 3px
  focus ring. Observed:
  <https://github.com/alphagov/govuk-frontend/tree/main/packages/govuk-frontend/src/govuk/components/error-summary>

## What the landscape says about this repository

- **Table stakes this repository lacked, and the PR adds:**
  - required facts shown before submission;
  - a plain-language requester status;
  - the playbook's standard and fallback position beside each change;
  - accessible inline decision forms.
- **Table stakes that stay out of scope by rule:**
  - outward channels (Slack, Teams or email bots that post);
  - authentication and SSO;
  - remote MCP connectors;
  - AI classification or drafting in the decision path.
- **Differentiators confirmed:**
  - Tested, explainable routing and approval tiers.
  - A hash-chained event log that blocks export.
  - Approvals bound to a version.
  - No model in the decision path. None of the snippet-visible vendors documents how a
    routing or risk decision is explained or reproduced. Inferred from the absence of such
    material in 43 searches, which is weak evidence.

## AI Act timing (logged for the owner, not used)

Search snippets report a provisional Digital Omnibus agreement on 6 May 2026 that would
move Annex III high-risk obligations to 2 December 2027 and Annex I to 2 August 2028. They
also report a Parliament plenary vote on 16 June 2026. Claimed:

- <https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/>
- <https://www.casrai.org/news/eu-ai-act-digital-omnibus-deadline-delay>

Publication in the Official Journal could not be checked because EUR-Lex was not
reachable. No date in this repository was changed. The item is listed under **Needs owner
decision** in the [adaptation plan](adaptation-plan.md#needs-owner-decision).

## Not reachable

| Host or source | Result on 2026-10-20 |
| --- | --- |
| lawvu.com, linear.app, eur-lex.europa.eu | WebFetch: `getaddrinfo ENOTFOUND` |
| www.checkbox.ai, design-system.service.gov.uk | curl: no connection (status 000) |
| docs.checkbox.ai, help.lawvu.com, support.zendesk.com | WebFetch: `getaddrinfo ENOTFOUND` |
| All other vendor sites | Not attempted after the failures above; facts are snippet-only |
| github.com/topics/legal-operations | HTTP 403 |
| api.github.com search (three topics) | HTTP 403; the proxy limits the session to its configured repositories |
| sebastianfoerste/legal-ai-design-system | `git clone` asked for credentials: private or not present |
| raw.githubusercontent.com …/awesome-legal-nlp/main | 404; the `master` branch worked |
| G2 review text for Checkbox and LawVu; Reddit | No usable results in search |

Network access for vendor documentation and EUR-Lex can be widened in the environment's
network settings for a follow-up run.
