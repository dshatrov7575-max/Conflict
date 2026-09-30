# Copilot CLI Primary Executor R2

Status: `FROZEN_READY_CREDENTIAL_ONLY_BLOCKED`

R2 supersedes R1 before any cohort primary output.

R1 had two execution defects:
1. its referenced workflow file did not exist;
2. its model pins were not guaranteed by the Copilot CLI v1.0.89 command reference.

R2 keeps the scientific cohort and all frozen standalone packets unchanged.

## Pinned runtime

- Copilot CLI: `v1.0.89`
- Linux x64 release asset SHA-256:
  `c5c234ccba6fae2b7a9eae462caf628e86c21b5e6240ec2e885727fc148a1dcc`
- AI1: `gpt-6-astra`
- AI2: `claude-opus-5.5`
- substitution: FORBIDDEN

The pin correction was made before any new cohort primary output.

## Authentication

Personal repository: workflow uses repository Actions secret `COPILOT_GITHUB_TOKEN`.

Required token type: user-owned fine-grained PAT with account permission `Copilot Requests`.

Preflight run 36715770075 showed this secret absent. Therefore the execution workflow is not triggered yet.

## Isolation

Each role runs in a separate GitHub-hosted matrix job and fresh VM.

The workflow:
- checks out the exact branch head only to obtain the frozen standalone bytes;
- copies exactly one standalone prompt into an isolated runner directory;
- changes into an empty working directory outside the checkout before invoking the model;
- creates a fresh `COPILOT_HOME`;
- disables built-in MCPs;
- restricts model-visible tools to `view`, with no useful files in the working directory;
- uses one non-interactive Copilot invocation;
- does not provide sibling outputs, prior R2/episode results, coordinator notes or known outcome;
- does not permit web access.

## Output

`copilot -s` stdout is written directly to the frozen role's expected JSON filename.

No cleanup or repair occurs:
- no Markdown stripping;
- no JSON repair;
- no coordinator edits;
- no retry because output is UNKNOWN, disagreement, invalid JSON or unexpected content;
- no model substitution.

Each matrix job uploads the raw file as a GitHub Actions artifact. The collection job downloads all available role artifacts and runs the frozen intake/comparison tooling. It does not fabricate missing roles.

## Trigger

Workflow file:
`.github/workflows/ai-only-primary-executor-r2.yml`

Trigger file:
`.github/ai-only-primary-executor-trigger-r2.txt`

The workflow runs only when that trigger file is created/changed on the research branch, or via manual workflow dispatch.

The trigger file remains absent while `COPILOT_GITHUB_TOKEN` is absent.

No auto-merge.
