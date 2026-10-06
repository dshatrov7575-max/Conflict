# VIRTUAL_HUMAN_PRECHECK_V1

Prepared before any virtual-human response.

Purpose: use two frontier models as simulated independent reviewers to reduce later manual exception-review workload while preserving at least one living-human verification for every unit.

Run:
1. VH1_GPT6_PRO.md in a new GPT-6 Pro chat.
2. VH2_CLAUDE_FABLE_5_1.md in a new Claude Fable 5.1 chat.
3. Save returned JSONs unchanged.
4. Run compare_virtual_humans.py.
5. Generate neutral human packets according to HUMAN_LOAD_MINIMIZATION_RULES_V1.

Do not show VH1 and VH2 each other's answers. Do not show living reviewers AI conclusions; only neutral evidence supplements may be carried forward.
