# PassKey — Findings / Known Issues

Durable record of passkey/Cognito issues that recur, with root cause and the exact
fix so re-diagnosis is cheap. These two were originally logged in the myBacklog
findings file (as F-002 / F-003); that file is transient, so the authoritative copy
lives here with the passkey work. Code and steering reference THIS file.

---

## F-002 — Passkey registration fails with `RelyingPartyMismatch` after Cognito work

**Status:** Fixed 2026-10-07. Recurs whenever the pool's WebAuthn config is reset.

**Symptom:** Registering a passkey from the app fails. Browser console:

```
associateWebAuthnCredential error: RelyingPartyMismatch:
Relying party does not match current domain.
  at async registerPasskey (authService.ts)
  at PasskeySettings.tsx
```

The `CredentialCreationOptions` returned by Cognito contained:

```json
"rp": { "id": "myadmin-6x2848jl.auth.eu-west-1.amazoncognito.com", ... }
```

**Root cause:** The production User Pool `eu-west-1_Hdp40eWmu` (`myAdmin`, personal
account `344561557829`) had **no `WebAuthnConfiguration` block** —
`get-user-pool-mfa-config` returned only `{"MfaConfiguration": "OFF"}`. With no explicit
`RelyingPartyId`, Cognito defaults the RP ID to the **hosted-UI domain**
(`myadmin-6x2848jl.auth.eu-west-1.amazoncognito.com`). But the app registers passkeys
directly (Amplify v6 `associateWebAuthnCredential`) from
`https://petergeers.github.io/myAdmin/`, NOT from the hosted UI. WebAuthn requires the
RP ID to equal the page's origin host or a registrable parent of it. The Cognito domain
is neither → `RelyingPartyMismatch`.

This is why it "breaks again after some work on Cognito": the WebAuthn RP ID is NOT in
Terraform (the AWS provider doesn't support it — same gap as the `SignInPolicy`
`AllowedFirstAuthFactors` note in `infrastructure/cognito.tf`). Any `set-user-pool-mfa-config`
call, pool re-create, or console change that omits the WebAuthn block silently reverts
the RP ID to the hosted-UI default.

**Fix (what was applied):**

```bash
aws cognito-idp set-user-pool-mfa-config \
  --user-pool-id eu-west-1_Hdp40eWmu \
  --mfa-configuration OFF \
  --web-authn-configuration 'RelyingPartyId=petergeers.github.io,UserVerification=preferred' \
  --profile personal --region eu-west-1
```

RP ID must be `petergeers.github.io` (the full host). It cannot be `github.io` —
that's on the Public Suffix List, so browsers reject it as an RP ID.

Verify:

```bash
aws cognito-idp get-user-pool-mfa-config \
  --user-pool-id eu-west-1_Hdp40eWmu \
  --profile personal --region eu-west-1 --output json
# expect: WebAuthnConfiguration.RelyingPartyId == "petergeers.github.io"
```

**Permanent fix — IMPLEMENTED 2026-10-07.** Both non-Terraform post-apply steps (the
WebAuthn RP ID and `SignInPolicy.AllowedFirstAuthFactors`) are now asserted by
`null_resource.cognito_passkey_post_apply` in `infrastructure/cognito.tf`. It runs the
two `aws cognito-idp` commands via `local-exec` on every `terraform apply` and re-triggers
when the pool, app client, or `var.passkey_relying_party_id` changes — so the RP ID can no
longer silently revert to the hosted-UI default. The RP ID and CLI profile are variables
(`passkey_relying_party_id` = `petergeers.github.io`, `cognito_cli_profile` = `personal`)
in `variables.tf`; `hashicorp/null` was added to `main.tf`. `terraform validate` passes.
Caveats: the `local-exec` runs the AWS CLI on the apply host (needs the `personal` profile),
and if a custom app domain is ever adopted the RP ID variable must change to that host, in
lockstep with the Cognito callback/logout URLs. Local passkey testing still needs
`RelyingPartyId=localhost` (per-origin), which the single prod RP ID does not cover.

**Scope / related:** `infrastructure/cognito.tf` (RP ID not expressible in TF),
`frontend/src/services/authService.ts` (`registerPasskey`),
`frontend/src/components/settings/PasskeySettings.tsx`. Account/pool facts per steering
`23-aws-accounts.md` (Pool A = `eu-west-1_Hdp40eWmu`, profile `personal`). See also
`tasks.md` §1.4a.

---

## F-003 — `update-user-pool --policies` silently DETACHES the PreTokenGen trigger

**Status:** Hit and fixed 2026-10-07 (during the F-002 permanent-fix work). High severity:
it strips `custom:entitlements` from every token platform-wide.

**Symptom:** After running the F-002 passkey automation (an `aws cognito-idp
update-user-pool` call that set `SignInPolicy`), the pool's `LambdaConfig` came back `{}` —
the V2 Pre-Token-Generation trigger (`pretokengen-prod`, the Lambda that stamps
`custom:entitlements` onto Pool A tokens) had vanished. New tokens would lack entitlements,
breaking module-plane authorization for every tenant.

**Root cause:** `aws cognito-idp update-user-pool` **REPLACES the entire pool
configuration**, not just the flags you pass. Calling it with only `--policies` (and no
`--lambda-config`) resets `LambdaConfig` to empty, detaching the trigger. This is documented
in `sam/pretokengen/DEPLOY.md` ("update-user-pool is picky: include settings that must
persist"), but the first version of `null_resource.cognito_passkey_post_apply` missed it.
The trigger is deliberately NOT in Terraform (it's owned by `sam/pretokengen` + a manual
identity-account attach — two-account split, see DEPLOY.md), so nothing else re-adds it.

**Immediate recovery (re-attach the trigger):**

```bash
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  aws cognito-idp update-user-pool --user-pool-id eu-west-1_Hdp40eWmu \
    --lambda-config '{"PreTokenGenerationConfig":{"LambdaVersion":"V2_0","LambdaArn":"arn:aws:lambda:eu-west-1:506221081911:function:pretokengen-prod"}}' \
    --profile personal --region eu-west-1
```

**Permanent fix (in `null_resource.cognito_passkey_post_apply`, cognito.tf):** before the
`update-user-pool` call, READ the current `LambdaConfig` and PASS IT BACK UNCHANGED via
`--lambda-config`, so the trigger is preserved whether or not it is attached. A post-step
re-reads `LambdaConfig` and FAILS LOUD (`exit 1`) if the trigger was lost. Verified by the
`terraform apply` log: `Preserving LambdaConfig: {PreTokenGeneration ... pretokengen-prod}`
→ update → `LambdaConfig preserved: {... pretokengen-prod}`. Also protected at the TF layer
by `lifecycle { ignore_changes = [lambda_config, web_authn_configuration] }` on the pool,
so `terraform plan` never shows a destroy for the trigger.

**Lesson:** NEVER call `update-user-pool` with a partial config. Any script touching a
Cognito pool via `update-user-pool` must first read and round-trip every block it is not
intentionally changing (`LambdaConfig` especially). Prefer the narrow APIs
(`set-user-pool-mfa-config` only touches MFA/WebAuthn and is safe) when they exist.

**Scope / related:** `infrastructure/cognito.tf` (the null_resource + lifecycle block),
`sam/pretokengen/DEPLOY.md` (trigger ownership + the picky-update warning), steering
`23-aws-accounts.md` (two-account split + the `update-user-pool` guardrail; Pool A says
"no trigger" baseline — now carries one).
