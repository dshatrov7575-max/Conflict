# Copilot CLI Executor Credential Bootstrap R1

**Status:** `OWNER_ONE_TIME_ACTION_REQUIRED`

This is the only required manual prerequisite for the prepared executor. The owner does **not** need to copy any of the eight scientific prompts.

## Why this is required

The repository is personally owned. The prepared GitHub Actions executor cannot use the repository's built-in `GITHUB_TOKEN` for Copilot CLI inference in this personal-repository configuration.

The preflight confirmed that these repository secrets are currently absent:
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `OPENROUTER_API_KEY`
- `COPILOT_GITHUB_TOKEN`
- `PERSONAL_ACCESS_TOKEN`

The frozen executor uses only `COPILOT_GITHUB_TOKEN`.

## One-time owner action

1. Open GitHub personal settings.
2. Create a **fine-grained personal access token**.
3. Resource owner: the owner's personal GitHub account.
4. Repository access: restrict the token to repository `dshatrov7575-max/Conflict` if the UI permits the required Copilot permission with that scope.
5. Add the **Copilot Requests** permission required by GitHub Copilot CLI.
6. Create the token.
7. Open repository:
   `dshatrov7575-max/Conflict` → Settings → Secrets and variables → Actions.
8. Create a new repository secret with the exact name:
   `COPILOT_GITHUB_TOKEN`
9. Paste the token value and save.

Do not paste the token into ChatGPT, Google Drive, GitHub issues, PR comments, source files, or task documents.

## After the secret exists

No other owner action is required.

The coordinator will:
1. rerun the no-value credential preflight;
2. verify only that `COPILOT_GITHUB_TOKEN` is present;
3. create/update `.github/ai-only-primary-executor-trigger.txt`;
4. automatically launch the frozen 8-job matrix;
5. preserve raw outputs unchanged;
6. run frozen comparators and cohort intake;
7. commit only run artifacts to the research branch;
8. keep PR #123 Draft and unmerged.

## Frozen executor

- workflow: `.github/workflows/ai-only-primary-executor-r1.yml`
- workflow Git blob: `4b222e521ecd081aeddfb0108a1b978211cb91b5`
- GitHub Copilot CLI: `v1.0.89`
- Linux x64 SHA-256:
  `c5c234ccba6fae2b7a9eae462caf628e86c21b5e6240ec2e885727fc148a1dcc`
- AI1: `gpt-5.6-sol`
- AI2: `claude-fable-5-1`
- model substitution: FORBIDDEN
- retry count: 0

## Cost note

The eight model calls consume GitHub Copilot AI credits under the GitHub account/plan associated with the PAT. If either pinned model is unavailable under that plan, the corresponding role fails and remains unresolved; the workflow does not downgrade or substitute a model.

## Security boundary

The workflow never prints or commits the PAT. The credential is available only to the Copilot CLI process through the Actions secret environment.

The scientific primary outputs remain separate from the credential and are stored as immutable run artifacts/results.
