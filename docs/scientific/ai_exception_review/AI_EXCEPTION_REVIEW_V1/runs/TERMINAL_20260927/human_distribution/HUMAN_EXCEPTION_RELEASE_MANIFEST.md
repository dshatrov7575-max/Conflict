# HUMAN_EXCEPTION_RELEASE_MANIFEST

Status: PREPARED_NOT_RELEASED

Source run: `TERMINAL_20260927`  
Source packet: `../HUMAN_EXCEPTION_PACKET.md`  
Queue size: 42 units  
Reason for queue: `SESSION_OUTCOME_CONTAMINATION_ALL_UNITS_QUARANTINED`

Distribution:
- E1 receives only `HUMAN_EXCEPTION_PACKET_E1.md` and fills `HUMAN_EXCEPTION_RESPONSE_E1.json`.
- E2 receives only `HUMAN_EXCEPTION_PACKET_E2.md` and fills `HUMAN_EXCEPTION_RESPONSE_E2.json`.
- E1 and E2 must not see each other's answers.
- Neither packet contains AI answers or AI voting.
- These reviewers are exception reviewers, not the later formal H1/H2 POS/KVS coders.
- Release of frozen H1/H2 remains unchanged and is not authorized by this manifest.

No human work is started merely by committing these files.

## Frozen pre-release comparison protocol

Before any E1/E2 response is collected, the following were frozen:
- `HUMAN_EXCEPTION_UNIT_REGISTRY.json` — exact 42-unit registry;
- `HUMAN_EXCEPTION_REVIEW_PROTOCOL_V1.md` — independence, routing, and scientific-boundary rules;
- `HUMAN_EXCEPTION_RESPONSE_SCHEMA_V1.json` — response structure and attestations;
- `compare_human_exception_results.py` — deterministic coordinator comparator.

Comparator self-test was executed on the authorized Windows device on 2026-09-28 before human responses and returned PASS for the four routing cases RR / NN / RN / HN.

The comparator never changes admission automatically and never computes inter-coder reliability. Any double-human RESOLVED result remains a coordinator-verification candidate.

