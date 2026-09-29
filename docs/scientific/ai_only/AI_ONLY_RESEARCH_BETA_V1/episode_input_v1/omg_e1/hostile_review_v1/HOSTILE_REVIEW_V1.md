# OMG Episode E1 — internal hostile scientific review V1

**Status:** INTERNAL_COORDINATOR_HOSTILE_REVIEW / NOT AN INDEPENDENT EXTERNAL REVIEW  
**Object:** completed `AI_ONLY_SINGLE_PTN_EPISODE_SCENARIO` for 26 May–28 June 2011  
**Review date:** 2026-09-29

## Verdict

| Layer | Verdict | Reason |
| --- | --- | --- |
| Deterministic calculation/replay | PASS | Exact pinned Core replay is reproducible; snapshot/result digests are recorded. |
| Narrow source provenance | PARTIAL PASS | Worker P1 replay is strong; company P2 supports content-level historical coding but not byte identity as served in 2011. |
| Primary coding reproducibility | FAIL | The two primary coders agreed on 0/4 entries. All final values were produced only after coordinator targeted review. |
| Factor adjudication independence | PARTIAL / HIGH RISK | The coordinator that assembled the package also resolved all four disagreements. This is permitted by the frozen workflow but is not independent replication. |
| Temporal construct | PARTIAL / NOT PROVEN AS SYNCHRONOUS STATE | A 26 May worker statement and a 28 June company statement are combined inside one episode without a frozen within-episode persistence/carry-forward rule. |
| Weight transparency | PASS | RGU/KVPTN are disclosed exogenous analytic design inputs. |
| Weight robustness | FAIL AS ROBUST CLAIM | Positive-RGU `Pol` spans 9.09090909–50. Equal weights produce the upper endpoint. |
| Generalization/prediction | NOT PROVEN | One selected case, one PTN, two actors, no negative control or holdout. |
| External scientific release | HOLD | Safe only as a bounded technical/research demonstration with the existing narrow label and limitations. |

## Major findings

### H1. Zero primary consensus

The frozen comparator routed all four entries to targeted review: AI1 returned four `UNKNOWN`; AI2 returned four numeric values. Therefore the final record is not model consensus. The AI1 objections were not frivolous: one worker-context hash was mislabeled, and the company provenance chain was not fully visible in the standalone packet.

**Consequence:** this run demonstrates that a coordinator can repair and adjudicate a package; it does not demonstrate independent coding reproducibility.

### H2. Coordinator adjudication carries the whole result

The single permitted targeted-review round changed the effective state from 0/4 numeric to 4/4 numeric after coordinator provenance verification and semantic adjudication. Original outputs remained immutable, but all released values depend on coordinator judgment.

**Consequence:** the result must be described as `coordinator-verified AI-coded episode values`, not as agreement between two frontier models.

### H3. Within-episode temporal aggregation is underspecified

Worker evidence is dated 26 May; the formal company response is dated 28 June. The package forbids carry-forward beyond the episode, but it does not define whether a statement at the episode start remains active at the episode end or whether two non-simultaneous source statements may be treated as one contemporaneous actor profile.

**Consequence:** the calculation is a bounded episode synthesis, not a point-in-time state. A future contract must choose one of: exact-date matching, explicit validity intervals, event-phase aggregation, or separate time slices.

### H4. Company KVS=5 is the most fragile factor

The rubric defines KVS=5 as explicit inclusion of the issue in an actor's formal demand or decision set. The company release rejects wage demands and sets a procedure for dialogue, but whether this constitutes the company's own formal decision set is interpretive. AI1 explicitly rejected the numeric KVS predicate.

This value is high leverage: without company KVS the episode is not calculation-eligible under the release gate; with KVS=5 and equal RGU, the two effective actor weights become exactly equal.

### H5. Equal baseline maximizes polarization in this configuration

For fixed `POS=(-5,+5)` and `KVS=(5,5)`, with positive actor weights `r_w,r_c`:

`Pol = 100 × min(r_w,r_c) / (r_w+r_c)`.

The equal baseline `r_w=r_c=1` therefore gives the maximum possible `Pol=50` for this factor configuration. It is transparent and symmetric, but it is not substantively neutral with respect to the polarization statistic.

### H6. Result is highly design-sensitive

The preregistered positive-RGU family yields `Pol` from 9.09090909 to 50.00000000. No justified robustness criterion was frozen, so the package correctly cannot call the result robust.

### H7. Post-result factor sensitivity exposes additional fragility

Keeping worker `KVS=5`, equal RGU and `POS=(-5,+5)`, alternative company KVS anchors would yield:

| Company KVS | Pol |
| ---: | ---: |
| 0 | 0.00000000 |
| 2 | 28.57142857 |
| 5 | 50.00000000 |
| 8 | 38.46153846 |
| 10 | 33.33333333 |

This is an exploratory post-result diagnostic, not a preregistered analysis and not permission to replace the verified factor. It shows why KVS adjudication cannot be treated as a minor detail.

### H8. Coarse POS anchors create saturation

At equal effective weights, worker `POS=-5` and company `POS=+5` produce `Pol=50`. Changing only one side from magnitude 5 to 10 leaves `Pol=50`; the stronger side changes `A/B`, but the smaller opposing component controls `Pol`. The metric therefore measures balanced opposing weighted mass, not generic conflict intensity.

### H9. Selection and topology remain narrow

The episode includes two actors and one PTN selected after the historical case and outcome are known to the coordinator. Coders were instructed not to use outcome knowledge, but source/episode selection was not outcome-blind. Residents, local and central authorities, other companies, unions as separate actors, and coercive actors are outside the topology.

**Consequence:** no claim about Zhanaozen as an area, the full conflict system, prediction, or causal explanation is supported.

## Safe interpretation

The package supports only this statement:

> Under the frozen AI-only episode contract, the coordinator-verified provisional source-statement coding and equal exogenous weight baseline produced a reproducible single-PTN scenario result `Pol=50`; across the frozen positive-RGU design grid, `Pol` ranged from 9.09090909 to 50.00000000.

It does not support “the true polarization was 50”, “UNO predicted the conflict”, “the model is validated”, or “two models independently agreed”.

## Final gate

- **Internal technical demonstration:** PASS.
- **Bounded AI-only research scenario:** PASS WITH MAJOR LIMITATIONS.
- **External scientific claim about historical area-level conflict or predictive validity:** HOLD.
- **Next scientific requirement:** prospective C2 episode contract with complete coder-visible provenance, explicit within-episode time semantics, clarified company-response KVS rule, and independent virtual tie-breaker rules frozen before coding.
