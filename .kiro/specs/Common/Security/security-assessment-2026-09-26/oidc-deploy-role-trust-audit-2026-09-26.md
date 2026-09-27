# OIDC Deploy-Role Trust Policy Audit — `NonprofitDeployRole` (risk S2)

**Date:** 2026-09-26
**Spec task:** L2 — Verify + document the SAM OIDC deploy-role trust policy
**Account:** 506221081911 (nonprofit / data account), region `eu-west-1`
**Repo:** `PeterGeers/myAdmin`

## Purpose

Audit the GitHub OIDC trust policy of `NonprofitDeployRole` (risk **S2**). The role is
assumed by the SAM deploy workflows via short-lived STS credentials (no stored secrets).
The concern: if the role's trust condition uses a broad `sub` wildcard, any branch, fork,
or PR run in the repo could assume the deploy role. It must be pinned to the `main` branch
ref only.

This audit records the **repo-verifiable** facts. The live IAM trust JSON check is
**outstanding** (see Status) — the `nonprofit-deploy` credential path is unavailable in the
environment where this note was produced, so `aws iam get-role` could not be run.

## Repo-verified facts

Two workflows assume `NonprofitDeployRole` via `aws-actions/configure-aws-credentials@v4`
using GitHub OIDC. A third deploy workflow (`deploy-frontend.yml`) does **not** touch this
role (it deploys to GitHub Pages, not the AWS data account).

### `.github/workflows/deploy-sam-members.yml`

| Fact | Value | Location |
| --- | --- | --- |
| Trigger event | `push` to `branches: [main]` (+ `workflow_dispatch`) | L13–L20 (`on:` / `push:` / `branches` L15; `workflow_dispatch` L20) |
| Path filters | `sam/members/**`, `sam/shared/**`, this workflow file | L16–L19 |
| `permissions` block | `id-token: write`, `contents: read` | L23–L25 |
| Role to assume | `arn:aws:iam::506221081911:role/NonprofitDeployRole` | L56 |
| AWS region | `eu-west-1` | L57 |
| Audience | not set → provider default `sts.amazonaws.com` | (no `audience:` key present) |

### `.github/workflows/deploy-sam-pretokengen.yml`

| Fact | Value | Location |
| --- | --- | --- |
| Trigger event | `push` to `branches: [main]` (+ `workflow_dispatch`) | L19–L26 (`on:` / `push:` / `branches` L21; `workflow_dispatch` L26) |
| Path filters | `sam/pretokengen/**`, `sam/shared/**`, this workflow file | L22–L25 |
| `permissions` block | `id-token: write`, `contents: read` | L29–L31 |
| Role to assume | `arn:aws:iam::506221081911:role/NonprofitDeployRole` | L62 |
| AWS region | `eu-west-1` | L63 |
| Audience | not set → provider default `sts.amazonaws.com` | (no `audience:` key present) |

### Assessment of the repo-side facts

- **Permission scope is minimal and correct for OIDC deploy.** Both workflows declare only
  `id-token: write` (required to mint the OIDC token) and `contents: read` (required for
  `actions/checkout`). No broad write scopes (`packages:`, `deployments:`, `pull-requests:`,
  etc.) are granted. ✅
- **Trigger branch is `main`.** Both workflows fire only on `push` to `main` (plus a manual
  `workflow_dispatch`). This is the branch the role's trust `sub` condition **should** be
  pinned to. Note: GitHub permissions/branch scoping in the workflow does **not** by itself
  constrain which refs can assume the role — that enforcement lives in the IAM trust policy,
  which is what still needs the live check below.
- **Role + region are consistent** across both workflows: `NonprofitDeployRole` in account
  `506221081911`, region `eu-west-1`.
- **Audience** is not explicitly set, so the action uses its default `sts.amazonaws.com`,
  which is the value the trust policy's `aud` condition must match.

## Verification criterion (what the live trust policy MUST show)

The deployed `AssumeRolePolicyDocument` for `NonprofitDeployRole` must satisfy **all** of:

1. Federated principal is the GitHub OIDC provider:
   `arn:aws:iam::506221081911:oidc-provider/token.actions.githubusercontent.com`.
2. Audience condition (`StringEquals`) pins:
   `token.actions.githubusercontent.com:aud` = `sts.amazonaws.com`.
3. Subject condition pins the **exact branch ref** (NOT a wildcard):
   `token.actions.githubusercontent.com:sub` = `repo:PeterGeers/myAdmin:ref:refs/heads/main`
   - **FAIL** if it is a wildcard such as `repo:PeterGeers/myAdmin:*` (would let any
     branch / PR / tag / environment in the repo assume the deploy role), or if it uses
     `StringLike` with a `*` that broadens beyond the single `main` ref.

## Status: LIVE IAM CHECK OUTSTANDING ⚠️

The actual deployed trust JSON was **NOT verified**. `aws iam get-role --role-name
NonprofitDeployRole` (profile `nonprofit-deploy`, account 506221081911) could **not** be run
in this environment — the `nonprofit-deploy` credential path is unavailable and the call
hangs. The live verification is therefore **deferred to a human with working
`nonprofit-deploy` credentials**.

### Command a human should run

Run from the repo root on WSL. The `env -u …` strip is required because the repo-root
`.env` exports static `personal`-account keys + a local DynamoDB endpoint that otherwise
override `AWS_PROFILE` and silently target the wrong account:

```bash
env -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \
  aws iam get-role --role-name NonprofitDeployRole --output json
```

Sanity-check identity first (must print `506221081911`, NOT `344561557829`):

```bash
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  aws sts get-caller-identity --profile nonprofit-deploy --region eu-west-1 --output json
```

### Paste the result here

Paste the `Role.AssumeRolePolicyDocument` from the `get-role` output:

```json
(paste AssumeRolePolicyDocument here)
```

**Verdict against the criterion above:**

- [ ] Federated principal = GitHub OIDC provider in account 506221081911
- [ ] `aud` = `sts.amazonaws.com`
- [ ] `sub` pinned to `repo:PeterGeers/myAdmin:ref:refs/heads/main` (no wildcard)

**PASS / FAIL:** _______________  (verified by: __________ on: __________)

## Remediation — if the trust `sub` is too broad

If the live trust policy uses a wildcard (e.g. `repo:PeterGeers/myAdmin:*`) or otherwise
allows refs beyond `main`, tighten the condition to pin the exact branch ref:

```json
{
  "Condition": {
    "StringEquals": {
      "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub": "repo:PeterGeers/myAdmin:ref:refs/heads/main"
    }
  }
}
```

Use `StringEquals` (exact match) for the `sub`, not `StringLike` with a `*`. This role is
assumed only by pushes to `main` in the two SAM deploy workflows, so a single exact ref is
sufficient. After tightening, confirm a `main` deploy still succeeds and that a non-`main`
run can no longer assume the role. This trust policy is managed **outside this repo**
(account 506221081911), so the change is applied in IAM, not in a repo file.
