# KBM E02 demand→response dyad — evidence recovery candidate R1

**Status:** `DISCOVERY_ONLY_AUTHENTICATION_PENDING_NOT_FROZEN_FOR_PRIMARY`  
**Route:** `AI_ONLY_RESEARCH_BETA_V1`  
**Candidate ID:** `KBM_E02_DYAD_CANDIDATE_R1`

## Purpose

Identify a second narrow pay-dispute dyad that may become fully numeric without carrying any dated statement to 15.12.2011 and without repairing UNKNOWN by assumption.

No factor value is assigned by this recovery note. No CalculationSnapshot, RGU/KVPTN choice, Pol or UNO is produced.

## Candidate temporal object

Proposed object only; not yet frozen:

- t0: 2011-05-21, `AOV2_KBM_STRIKERS`, E02 pay demand source statement `D01-FPAY`;
- t1: 2011-05-26, `KBM_MANAGEMENT_FORMAL_RESPONSE`, company press-release response;
- simultaneous snapshot: false;
- carry-forward: NONE;
- interpretation: dated demand→response comparison only.

## Worker-side basis already present in R2

R2 contains `D01-FPAY` with exact text: `strikers are demanding a pay rise`, actor scope limited to the Qarazhanbas strike context. The completed R2 final record coded `AO2S-C1-03` as POS=-5 and KVS=5.

Inheritance is only potentially permissible if a future frozen dyad keeps the same actor scope, E02 reference statement and source identity. Otherwise workers must be recoded prospectively.

## Newly recovered company-side material

### 2011-05-14 — Kazinform / KBM press service
URL: https://www.inform.kz/ru/zavershena-akciya-protesta-chlenov-profsoyuza-rabotnikov-ao-karazhanbasmunay_a2380062

The article explicitly attributes the material to the KBM press service. It records that the company considered the 1.8 coefficient and MSOT-based harmful-conditions demand unfounded, while also reporting two commission meetings where some collective-agreement issues had been considered and certain agreements reached, pending worker approval.

### 2011-05-19 — Kazakhstan Today / KBM statement
URL: https://www.kt.kz/rus/society/bolee_700_rabotnikov_kbm_ats_i_tms_prekratili_rabotu_i_prinjali_uchastie_v_nesankcionirovannoj_zabastovke_1153538413.html

The article reproduces a KBM statement that the company regularly raised salary rates, describes cumulative 2007–2011 wage increases, calls the disputed demands unfounded and states readiness for dialogue under legal procedures.

### 2011-05-24 — Vremya / contemporaneous republication
URL: https://time.kz/news/archive/2011/05/24/ayda-bastovat%21

This contemporaneous article reproduces the same company salary-history position, including the claimed 59.5–90.1% wage-growth range and current tariff figures.

### 2011-05-26 — Kazinform / KBM press release
URL: https://www.inform.kz/ru/resheniem-rayonnogo-suda-zabastovka-rabotnikov-ao-karazhanbasmunay-too-argymaktransservis-i-too-tulparmunayservis-priznana-nezakonnoy_a2382946

The article explicitly says the information is from the KBM press service. It reports: the wage-coefficient demands were considered unfounded; KBM says it regularly raises salaries and had increased them by 59.5–90.1% over 2007–2011; management had repeatedly proposed settlement at the negotiating table.

## Why this candidate is promising

Unlike the superseded OMG V1.0.0 company material, the recovered KBM material contains not only rejection/rebuttal of worker demands but also descriptions of the company's own pay actions and negotiation decisions. This may satisfy the reactive-actor salience predicate, but **no KVS value is preassigned here**.

## Remaining blockers

1. **Historical source authentication is not yet closed.** Current publisher archive pages and cross-publication consistency are strong content recovery, but this chat has not reproduced a pre-cutoff Wayback payload/hash or another already-approved historical-byte witness for the company statement.
2. **Actor-scope alignment is not yet frozen.** Some KBM releases discuss KBM together with ATS/TMS workers. A future dyad must not silently widen the worker actor beyond the scope of `D01-FPAY`.
3. **Temporal contract is not frozen.** The future object must be defined before coding and must remain a non-simultaneous demand→response dyad.
4. **No inheritance by convenience.** R2 worker values may be inherited only after exact identity/scope equivalence is proven in the new freeze record.

## Next gate

Before any blind primary run:
- authenticate at least one company-side historical witness under an existing approved provenance class or explicitly freeze a new provenance rule prospectively;
- freeze actor identities, exact t0/t1, E02 reference statement, source identities and common input SHA;
- create two independent standalone packets;
- forbid coordinator substitution, rerun-until-number and UNKNOWN→0.

Until then: `PROMISING_NOT_READY_FOR_PRIMARY_FREEZE`.
