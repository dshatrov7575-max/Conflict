# OMG E02 23–24 Nov 2011 negotiation episode — candidate R1

Status: PROMISING_AUTHENTICATION_PENDING_NOT_FROZEN_FOR_PRIMARY
Route: AI_ONLY_RESEARCH_BETA_V1
Candidate ID: OMG_E02_NOV24_NEGOTIATION_CANDIDATE_R1

## Why this candidate

This candidate is materially different from OMG V1.0.1/V1.0.2. It targets the documented 23–24 November 2011 negotiation episode with dismissed OMG worker representatives, not the May→June/August demand-response dyad.

It may allow two actor rows to be coded from the same bounded negotiation episode, reducing the temporal-gap problem. No POS/KVS value is assigned here.

## Candidate actor/PTN object

PTN: E02 — pay and social guarantees.

Proposed worker actor: DISMISSED_OMG_WORKER_REPRESENTATIVES_NOV2011.
Proposed counterparty: OMG_EMPLOYER_NEGOTIATION_RESPONSE_NOV2011.
Episode event window: 2011-11-23 through 2011-11-24.
Carry-forward: NONE.

## Evidence recovered

### Worker-side / agenda

A contemporaneous 24.11.2011 report says negotiations began on 23 November with worker representatives and employer/government participants, with concrete discussion of worker demands expected.

A 06.12.2011 report describing the 23–24 November meeting states that five agenda items were discussed and recorded in a protocol. The pay-related items included:
- application of the sector coefficient 1.8 in the collective and individual employment agreements;
- application of the territorial coefficient 1.7;
- collective-agreement/pay-regulation language incorporating those coefficients.

It separately reports reinstatement/compensation and management-removal items. This supports a prospectively narrow worker-representative actor rather than all workers.

### Counterparty / documented response

The same report states that the meeting reviewed employer documents and payroll calculations. It reports that:
- the sector coefficient 1.8 was already applied to production personnel covered by the relevant work conditions;
- the employer was paying the territorial coefficient 1.7 under the collective agreement;
- the 1.7 payment was described as a company-funded measure initiated by the employer rather than a statutory obligation.

This is potentially stronger for reactive-actor KVS than a mere rebuttal because it describes an employer's own pay implementation/resource-allocation decision. No numeric KVS is assigned here.

## Sources

- Yvision, 24.11.2011, "В Жанаозене вчера начались переговоры": https://yvision.kz/post/v-zhanaozene-vchera-nachalis-peregovory-208295
- Nomad / "Огни Мангистау", page 06.12.2011, "Итоги переговоров в ПФ Озенмунайгаз": https://nomad.su/?a=3-201112060023
- Nomad, page 30.11.2011, additional contemporaneous account: https://nomad.su/?a=3-201111300026

## Blockers before freeze

1. Reproduce at least one pre-cutoff preservation witness for the worker-side agenda and one for the employer-side response, or a single authenticated historical payload that contains both with sufficient attribution.
2. Resolve dependency: the 30.11 and 06.12 pages may depend on the same meeting protocol/reporting chain; do not count them as independent corroboration without proof.
3. Freeze exact actor identities and decide whether the event can be represented as a single-meeting multi-actor record or only as non-simultaneous source statements.
4. Freeze exact excerpts and common input SHA before any primary coding.
5. No inheritance from OMG V1.0.0 company KVS, no V1.0.1/V1.0.2 factor reuse, no UNKNOWN→0.

Until those gates close: PROMISING_NOT_READY_FOR_PRIMARY_FREEZE.
