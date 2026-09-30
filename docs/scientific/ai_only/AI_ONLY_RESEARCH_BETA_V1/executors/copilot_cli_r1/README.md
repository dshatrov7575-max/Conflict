# Copilot CLI Primary Executor R1

Status: `FROZEN_READY_CREDENTIAL_BLOCKED`

This executor is prepared for the already frozen four-lane / eight-role cohort.

## Authentication

The repository is personally owned. The workflow therefore requires a fine-grained GitHub PAT stored as the repository Actions secret:

`COPILOT_GITHUB_TOKEN`

The secret must include the GitHub Copilot Requests permission required by Copilot CLI. Standard OpenAI/Anthropic/OpenRouter API keys are not used.

At freeze time the secret is absent. The workflow is deliberately not triggered.

## Pinned executor

- GitHub Copilot CLI: `v1.0.89`
- Linux x64 release asset SHA-256:
  `c5c234ccba6fae2b7a9eae462caf628e86c21b5e6240ec2e885727fc148a1dcc`
- AI1 model: `gpt-5.6-sol`
- AI2 model: `claude-fable-5-1`
- model substitution: FORBIDDEN

## Independence

Each of the 8 primary roles runs as a separate GitHub Actions matrix job on its own fresh GitHub-hosted VM.

Each job:
- receives one exact frozen standalone file only;
- uses a unique fresh `COPILOT_HOME`;
- executes from an empty `RUNNER_TEMP` working directory outside the repository;
- exposes only the `read` tool to the model, with nothing useful to read in that directory;
- does not provide sibling outputs, prior R2/episode outputs, coordinator notes or the known outcome;
- uses no web-search or URL tool;
- makes one model invocation only.

## Output

Copilot CLI final stdout is preserved unchanged as the primary output file.

There is:
- no Markdown stripping;
- no JSON repair;
- no coordinator correction;
- no retry because of UNKNOWN, disagreement or malformed output;
- no replacement model.

If the executor itself fails (authentication/model unavailable/CLI error), that role remains unresolved; it is not replaced.

After all matrix jobs complete, the workflow runs the already frozen cohort intake/orchestrator. Raw primary outputs and deterministic derived artifacts are committed to the research branch only if produced.

## Trigger

The workflow listens for a push that changes only:

`.github/ai-only-primary-executor-trigger.txt`

That trigger file does not yet exist. Once the required secret is available, the coordinator can create/change the trigger file and start the cohort without asking the owner to shuttle eight prompts between chats.

No auto-merge is performed.
