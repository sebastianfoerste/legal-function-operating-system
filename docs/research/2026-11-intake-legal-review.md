# Intake wording: legal and policy review, November 2026

This memo settles owner decision 13 in the [adaptation plan](adaptation-plan.md): the
open questions about the wording of the bundled intake questions
(`src/legal_function_os/data/intake_questions.json`, [ADR 0006](../adr/0006-intake-question-files.md)).
On 2026-11-10 the owner asked for every open item to be decided as recommended, with
research where needed, and for the decisions to be taken here rather than handed back.

It is not legal advice. The page asks a requester for facts; legal reviews every file
and draws every conclusion. The wording below decides what a requester is asked to
report, never what the law says about their case.

## Method

- **Primary sources only.** Every quote below was fetched from EUR-Lex on 2026-11-10 or
  2026-11-11 and then fetched again, independently, by a second reviewer who checked it
  word for word. Links are to the EUR-Lex document; article, recital, paragraph or
  point numbers are given with each quote.
- **Blocked sources.** The network policy of the research environment blocked the EDPB,
  Curia, the Commission's site and national law sites. The EDPB guidelines on
  controllers and processors (07/2020), on transfers (05/2021) and on the right of
  access (01/2022) were therefore not read, and nothing below rests on them. Points that
  would need them are listed under [Left for legal](#left-for-legal).
- **No citations in the question file.** The questions carry no article number, date or
  citation. They ask for facts in plain words; citations live only here.
- **The safe direction.** Where a requester may be unsure, the wording steers them to the
  answer that adds review (Yes on the three decision flags, the higher value band), never
  to one that silently lowers it. This is the rule the owner confirmed on 2026-11-03.
- **Tags.** **Verified**: quoted from EUR-Lex as above. **Repository**: a fact about this
  repository's own code or data. **Decided**: a policy choice the owner delegated.

## 1. Who decides what the data is used for (DPA type)

**Decided.** `types.dpa.questions[0]` (`processing_role`):

- Label: "Who decides what the data is used for?" (was "Who decides how the data is used?").
- Hint (new): "This is not about whose software or systems handle it. If the other party
  will also use the data for its own purposes, for example to improve its products, or
  you are not sure, say so in “What do you need from legal?”."
- A fourth answer, "We decide together (we are joint controllers)", before "Not sure".
  The three existing answers are unchanged, so files saved before stay valid.

**Why.** The controller decides the purposes; a processor acts for the controller and on
its instructions. A software or hosting supplier always designs how its own system
works, so "who decides how" invites the answer "the other party", which saves "we are the
processor": usually the reverse of the truth. "What the data is used for" asks about
purposes, which a processor cannot have of its own. Joint control is its own status: it
needs an arrangement between the controllers, not an Art. 28 agreement, so legal needs to
know when the requester thinks it applies.

**Sources (Verified).**

- GDPR Art. 4(7)
  ([32016R0679](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679)):
  "‘controller’ means the natural or legal person, public authority, agency or other body
  which, alone or jointly with others, determines the purposes and means of the
  processing of personal data;"
- GDPR Art. 4(8): "‘processor’ means a natural or legal person, public authority, agency
  or other body which processes personal data on behalf of the controller;"
- GDPR Art. 28(3)(a): "processes the personal data only on documented instructions from
  the controller, including with regard to transfers of personal data to a third country
  or an international organisation, unless required to do so by Union or Member State law
  to which the processor is subject;"
- GDPR Art. 28(10): "if a processor infringes this Regulation by determining the purposes
  and means of processing, the processor shall be considered to be a controller in
  respect of that processing."
- GDPR Art. 26(1), first sentence: "Where two or more controllers jointly determine the
  purposes and means of processing, they shall be joint controllers."
- CJEU C-210/16 *Wirtschaftsakademie*, para 40
  ([62016CJ0210](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:62016CJ0210)):
  "The fact that an administrator of a fan page uses the platform provided by Facebook in
  order to benefit from the associated services cannot exempt it from compliance with its
  obligations concerning the protection of personal data."
- CJEU C-683/21 *Nacionalinis visuomenės sveikatos centras*, operative part, point 4
  ([62021CJ0683](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:62021CJ0683)):
  a fine may be imposed on a controller for a processor's operations "unless, in the
  context of those operations, that processor has carried out processing for its own
  purposes". This is why the hint asks whether the other party will use the data for its
  own purposes.

## 2. What counts as personal data (decision flag)

**Decided.** `fields.personal_data.hint`: "Information about a person, such as names, email
addresses or employee records. This includes data that can be linked to a person, such as
customer or user IDs, IP addresses, cookie IDs or location data, even if names have been
removed or replaced with codes. Not sure? Choose Yes and say why in “What do you need
from legal?”."

**Why.** The old examples all identified someone directly. A requester sharing only user
IDs, IP addresses or pseudonymised logs would answer a confident No, which removes the
MEDIUM reason "Personal data processed." and, with a transfer, the HIGH reason
(Repository: `src/legal_function_os/rules.py`). The hint names indirect identifiers and
coded data, and says nothing about when data stop being personal: that depends on who
holds the means to re-identify, which is legal's call.

**Sources (Verified).**

- GDPR Art. 4(1): "‘personal data’ means any information relating to an identified or
  identifiable natural person (‘data subject’); an identifiable natural person is one who
  can be identified, directly or indirectly, in particular by reference to an identifier
  such as a name, an identification number, location data, an online identifier or to one
  or more factors specific to the physical, physiological, genetic, mental, economic,
  cultural or social identity of that natural person;"
- GDPR Recital 30: "Natural persons may be associated with online identifiers provided by
  their devices, applications, tools and protocols, such as internet protocol addresses,
  cookie identifiers or other identifiers such as radio frequency identification tags."
- GDPR Recital 26: "Personal data which have undergone pseudonymisation, which could be
  attributed to a natural person by the use of additional information should be
  considered to be information on an identifiable natural person."
- CJEU C-582/14 *Breyer*, operative part, point 1
  ([62014CJ0582](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:62014CJ0582)):
  "a dynamic IP address registered by an online media services provider when a person
  accesses a website that the provider makes accessible to the public constitutes
  personal data within the meaning of that provision, in relation to that provider, where
  the latter has the legal means which enable it to identify the data subject with
  additional data which the internet service provider has about that person."
- CJEU C-413/23 P *EDPS v SRB*, para 86
  ([62023CJ0413](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:62023CJ0413)):
  "pseudonymised data must not be regarded as constituting, in all cases and for every
  person, personal data". The judgment interprets Regulation 2018/1725 (EU institutions);
  its para 52 requires the same reading as GDPR Art. 4(1). This is why the hint says
  "can be linked" and leaves the conclusion to legal.

## 3. Data outside the EEA (decision flag)

**Decided.** `fields.non_eea_transfer.hint`: "The EEA is the EU plus Iceland,
Liechtenstein and Norway, not the UK or Switzerland. Choose Yes if any organisation or
server outside the EEA, including a company in our group, holds, gets or sees any of the
data, or will, even just for support. Not sure? Choose Yes and say why in “What do you
need from legal?”."

`types.dpa.questions[2]` (`transfer_countries`) hint: "Include the countries where the
data is or will be held and where anyone who gets or sees it is based. If you do not
know, write not sure."

**Why.** The label already asks about data "sent to or accessed from outside the EEA";
the hint makes access concrete, including the other party itself, a group company and a
support team, and names the two neighbours requesters most often take to be inside. It
asks for facts and leaves the question whether there is a transfer to legal: where that
line falls is contested (below), and an unsure No would silently drop the Privacy routing
and the HIGH reason. Our own staff travelling abroad are deliberately not named: whether
that is a transfer is a legal conclusion, and naming it either way would flood the queue
or instruct a No. The "Not sure?" route still covers it.

**Sources (Verified).**

- EUR-Lex glossary, "European Economic Area (EEA)"
  ([glossary](https://eur-lex.europa.eu/EN/legal-content/glossary/european-economic-area-eea.html)):
  "The European Economic Area (EEA) groups together the 27 EU Member States and 3
  European Free Trade Association (EFTA) countries (Iceland, Liechtenstein and Norway) in a
  single market subject to the same rules."
- GDPR Art. 44: "Any transfer of personal data which are undergoing processing or are
  intended for processing after transfer to a third country or to an international
  organisation shall take place only if, subject to the other provisions of this
  Regulation, the conditions laid down in this Chapter are complied with by the
  controller and processor"
- CJEU C-311/18 *Schrems II*, para 83
  ([62018CJ0311](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:62018CJ0311)):
  "It follows that the operation of having personal data transferred from a Member State
  to a third country constitutes, in itself, processing of personal data within the
  meaning of Article 4(2) of the GDPR, carried out in a Member State"
- CJEU C-101/01 *Lindqvist*, para 71
  ([62001CJ0101](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:62001CJ0101)):
  no transfer "where an individual in a Member State loads personal data onto an internet
  page which is stored with his hosting provider which is established in that State or in
  another Member State, thereby making those data accessible to anyone who connects to the
  internet, including people in a third country." (Directive 95/46.)
- General Court T-354/22 *Bindl*, para 133
  ([62022TJ0354](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:62022TJ0354)):
  "access by the authorities of a third country, under the legislation of that country,
  to personal data processed in the EEA constitutes a transfer of personal data to a third
  country". (Regulation 2018/1725; under appeal.)
- Commission appeal, Case C-206/25 P, first ground
  ([62025CN0206](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:62025CN0206)):
  "the General Court misinterpreted and misapplied Article 46 EU-GDPR by using an
  incorrect test in determining whether the applicant’s personal data were transferred to
  a third country." No appeal judgment was on EUR-Lex on 2026-11-11.

## 4. Sub-processors (DPA type)

**Decided.** `types.dpa.questions[3]` (`sub_processors`) hint: "A sub-processor is another
company or contractor that the processor uses to handle some of the data, such as a
hosting or support provider, or a company in the processor's own group. Not sure? Choose
Yes and say why in “What do you need from legal?”."

**Why.** "Sub-processor" is a term of art; a requester may answer No because the other
party "does it all itself" while its host or support desk handles the data. "The
processor" works whichever side is the processor. Whether a given provider is a
sub-processor stays with legal.

**Sources (Verified).**

- GDPR Art. 28(2): "The processor shall not engage another processor without prior
  specific or general written authorisation of the controller."
- GDPR Art. 28(4), first sentence: "Where a processor engages another processor for
  carrying out specific processing activities on behalf of the controller, the same data
  protection obligations as set out in the contract or other legal act between the
  controller and the processor as referred to in paragraph 3 shall be imposed on that
  other processor"
- Commission Implementing Decision (EU) 2021/915, Annex, Clause 7.7(b)
  ([32021D0915](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32021D0915)):
  "Where the processor engages a sub-processor for carrying out specific processing
  activities (on behalf of the controller), it shall do so by way of a contract which
  imposes on the sub-processor, in substance, the same data protection obligations as the
  ones imposed on the data processor in accordance with these Clauses."

## 5. A person's request about their own data (privacy type)

**Decided.** `types.privacy_query.questions[1]` hint: "For example they asked what data you
hold about them, for a copy, to correct or delete it, to move it to another company, to
stop using it, or for someone to review a decision made by a computer. They might not use
legal words. Not sure? Choose Yes and say why in “What do you need from legal?”."

`types.privacy_query.questions[2]` hint: "The first date it reached our company or anyone
acting for us, for example a shared inbox, a colleague or a supplier, even if that was
before it reached you. Year, month and day, for example 2026-11-02. Not sure? Give the
earliest likely date and say why in “What do you need from legal?”."

**Why.** The time limit runs from receipt of a request under Articles 15 to 22, which
include portability and human review of an automated decision; the examples now cover
them in plain words. The date question asks for the earliest receipt, the conservative
fact whatever legal later decides about who received it.

**Sources (Verified).**

- GDPR Art. 12(3), first sentence: "The controller shall provide information on action
  taken on a request under Articles 15 to 22 to the data subject without undue delay and
  in any event within one month of receipt of the request."
- GDPR Art. 20(1), opening words: "The data subject shall have the right to receive the
  personal data concerning him or her, which he or she has provided to a controller, in a
  structured, commonly used and machine-readable format and have the right to transmit
  those data to another controller without hindrance from the controller to which the
  personal data have been provided"
- GDPR Art. 22(3), closing words: "at least the right to obtain human intervention on the
  part of the controller, to express his or her point of view and to contest the
  decision."

## 6. AI systems that affect people (AI type)

**Decided.**

- `types.ai_governance.questions[2]` hint: "For example hiring, managing staff, education,
  credit, insurance or access to a service. Not sure? Choose Yes and say why in “What do
  you need from legal?”."
- `types.ai_governance.questions[3]` hint: "Choose Yes only if that person understands the
  output, can change or overrule it, and does so when it looks wrong. Not sure, or only
  some outputs are checked? Choose No and say why in “What do you need from legal?”."

**Why.** The examples follow the AI Act's high-risk areas that an in-house requester is
likely to meet; managing staff was the clear gap. The human-check hint makes a Yes mean
something: understanding, the power to overrule, and actually using it. A Yes is
information for legal, not a finding that a decision is not solely automated or that
oversight duties are met.

**Sources (Verified).** AI Act, Regulation (EU) 2024/1689
([32024R1689](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689)):

- Annex III point 4(a): "AI systems intended to be used for the recruitment or selection
  of natural persons, in particular to place targeted job advertisements, to analyse and
  filter job applications, and to evaluate candidates;"
- Annex III point 4(b): "AI systems intended to be used to make decisions affecting terms
  of work-related relationships, the promotion or termination of work-related contractual
  relationships, to allocate tasks based on individual behaviour or personal traits or
  characteristics or to monitor and evaluate the performance and behaviour of persons in
  such relationships."
- Annex III point 3(a): "AI systems intended to be used to determine access or admission
  or to assign natural persons to educational and vocational training institutions at all
  levels;"
- Annex III point 5(b): "AI systems intended to be used to evaluate the creditworthiness
  of natural persons or establish their credit score, with the exception of AI systems
  used for the purpose of detecting financial fraud;"
- Annex III point 5(c): "AI systems intended to be used for risk assessment and pricing in
  relation to natural persons in the case of life and health insurance;"
- Art. 14(4)(d): "to decide, in any particular situation, not to use the high-risk AI
  system or to otherwise disregard, override or reverse the output of the high-risk AI
  system;"
- Art. 14(4)(b): "to remain aware of the possible tendency of automatically relying or
  over-relying on the output produced by a high-risk AI system (automation bias)"
- Art. 26(2): "Deployers shall assign human oversight to natural persons who have the
  necessary competence, training and authority, as well as the necessary support."
- GDPR Art. 22(1): "The data subject shall have the right not to be subject to a decision
  based solely on automated processing, including profiling, which produces legal effects
  concerning him or her or similarly significantly affects him or her."
- CJEU C-634/21 *SCHUFA*, operative part
  ([62021CJ0634](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:62021CJ0634)):
  a credit score is "‘automated individual decision-making’ within the meaning of that
  provision, where a third party, to which that probability value is transmitted, draws
  strongly on that probability value to establish, implement or terminate a contractual
  relationship with that person."

When these AI Act provisions apply is recorded, with its sources, in
`src/legal_function_os/raas_sources.py` (owner decision 5); this memo restates no date.
The research confirmed that record against the consolidated text and Regulation (EU)
2026/1744.

## 7. Uncapped liability (decision flag)

**Decided.** The flag means our side's liability is or would be uncapped.

- Label: "Is there unlimited liability on our side?" (was "Does the other party ask for
  unlimited liability?").
- Hint: "Choose Yes if they want no limit on our liability, if the draft sets no limit, or
  if some claims have no limit, for example data protection, confidentiality or
  intellectual property claims. Claims for fraud, deliberate wrongdoing, death or
  personal injury, or for payment of the agreed price do not count. Not sure? Choose Yes
  and say why in “What do you need from legal?”."
- The request contract's description of `uncapped_liability` says the same
  (`contracts/legal-request.v1.schema.json`; a description change, allowed within v1).
- The follow-up `liability_cap_discussed` asks "What limit on liability has been
  discussed, and which claims are outside it?".

**Why (Repository and Decided).** The rule's own reason is "Uncapped liability exposure."
(`rules.py`), which is about exposure, not about who asked. A draft silent on liability
usually creates the same exposure as an express request, and so does an uncapped
carve-out for data protection, confidentiality or IP. The repository's RaaS playbook
already escalates "Any uncapped exposure" and treats a separately capped super-cap as an
acceptable fallback (`raas_rules.py`); a separate higher cap is therefore not "uncapped".
The usual exceptions appear in almost every contract; counting them would make every
contract HIGH risk with General Counsel, and the flag would stop telling contracts apart.
Pilot scenario 03 ("unlimited supplier liability") stays Yes; scenario 02 ("300% liability
cap") stays No.

**Context (Verified), for the memo only.** Some carve-outs exist because the law does not
let the parties cap liability towards the injured person:

- GDPR Art. 82(4): "each controller or processor shall be held liable for the entire
  damage in order to ensure effective compensation of the data subject."
- Directive (EU) 2024/2853 (product liability), Art. 15
  ([32024L2853](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024L2853)):
  "Member States shall ensure that the liability of an economic operator pursuant to this
  Directive is not, in relation to the injured person, limited or excluded by a
  contractual provision or by national law."
- Transfer SCCs, Decision (EU) 2021/914, Annex, Clause 12(a) (Modules Two and Three)
  ([32021D0914](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32021D0914)):
  "Each Party shall be liable to the other Party/ies for any damages it causes the other
  Party/ies by any breach of these Clauses."

## 8. Value bands: basis and boundaries

**Decided: yearly basis.** `fields.value_band.hint`: "In euros, without VAT. If it runs for
more than a year or has no end date, use the highest yearly value and give the total and
how long it runs in “What do you need from legal?”. For a claim, use the amount claimed.
Not sure? Choose the higher band it could be in and say why in “What do you need from
legal?”." The request contract and `docs/INPUT_FORMAT.md` define the band the same way.

**Why (Repository).** The pilot's required fact is `annual_contract_value_eur`, and the
core contract question asks for the "Annual contract value in EUR", so a yearly band can
be checked against that number. The scenarios band EUR 42,000 as `<50k` and EUR 480,000
and EUR 610,000 as `250k-1m`; scenario 02 states a 36-month term, so a whole-term basis
(EUR 1.44 million) would put it in `>1m`, with a board note and the pilot exclusion,
contradicting that scenario. The pilot's standard liability cap is measured in the fees of
the preceding twelve months. A yearly figure also exists for contracts with no end date,
such as employment. The cost: a multi-year deal can stay below the board band while its
total is above it. The hint therefore asks for the total and the term, and legal can raise
the band. "Not sure? Choose the higher band" applies the owner's safe-direction rule.

EU law shows why "value" has to be defined (an analogy only: it does not govern a
company's own approvals). Directive 2014/24/EU, Art. 5(1)
([32014L0024](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32014L0024)),
values a public contract on "the total amount payable, net of VAT", including options and
renewals. That rule serves public procurement; this repository's thresholds are about
review effort, and its data are yearly.

**Decided: every band starts at its lower figure.** Exactly EUR 50,000 is `50k-250k`;
exactly EUR 250,000 and exactly EUR 1 million are `250k-1m`.

- The `50k-250k` label now reads "EUR 50,000 or more but under EUR 250,000" (it overlapped
  "EUR 250,000 to EUR 1 million" at EUR 250,000).
- The policy's sentences now agree with the bands (`default_policy.json`): "Value over
  EUR 1 million.", "Value from EUR 250,000 to EUR 1 million.", "Dispute value of
  EUR 250,000 or more." and "Value over EUR 1 million: add to board awareness list."
  The old "Dispute above €250k." contradicted the rule it explains.

**Why.** The rules apply a threshold "at or above" its band (`Policy.reaches()`), so every
rule set "from `250k-1m`" starts wherever that band starts; putting the boundary in the
higher band adds review, the safe direction. EU thresholds are likewise reached at the
figure itself: Directive 2014/24/EU, Art. 4 applies to procurements "estimated to be equal
to or greater than the following thresholds". (Two gap-free readings of the keys exist;
the choice between them rests on these reasons, not on the keys alone.)

## 9. The pilot's contract-changes label

**Decided.** The pilot's label for `requested_deviations`
(`supervised-agent/src/pilot/models.py`) and the core question both read "Changes the
other party asked for" (was "Changes the customer asked for"). Hint: "For example longer
payment terms or a higher limit on liability. Write none if there are none. If you do not
know, write not sure."

**Why (Repository).** The core type is "Customer or supplier contract", so "the customer"
was our own side whenever we buy. "The other party" stays true in the pilot, where the
other party is always the customer. The label appears in no golden file; a test keeps the
pilot and the page in step.

## Left for legal

These depend on a jurisdiction or on sources the research could not reach. The wording
above does not depend on any of them, because it asks for facts and leaves the conclusion
to legal.

- **Controller and processor in a given case.** The EDPB's "essential and non-essential
  means" distinction (Guidelines 07/2020) was not read. Whether a supplier's own use of
  the data (for example to improve its products) makes it a controller is case by case.
- **Pseudonymised data.** Whether a data set is personal data for a given recipient after
  C-413/23 P depends on who holds the means to re-identify.
- **Transfers.** Whether remote access or a travelling employee's access is a transfer;
  the EDPB's transfer guidelines (05/2021) were not read, and the *Bindl* test is under
  appeal (C-206/25 P, C-211/25 P).
- **Request receipt.** Whether receipt by a processor, a call centre or another group
  company starts the one-month period (EDPB 01/2022 not read). The page asks for the
  earliest date either way.
- **AI.** Whether a use falls in Annex III or the Art. 6(3) derogation, and whether a
  decision is solely automated under GDPR Art. 22 (the WP29/EDPB guidelines were not read).
- **Liability.** Which exceptions are "usual", what cannot be limited at all under the
  governing law, and whether a draft with no clause actually leaves liability unlimited
  there. Legal should align the hint's examples with its own playbook.
- **Value bands.** Whether the company's own signing-authority rules measure limits on
  total commitment; if they do, switch the bands to total value or check the total in the
  description.
