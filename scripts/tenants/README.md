# `scripts/tenants/` — per-tenant onboarding secrets

One directory per tenant holds that tenant's **onboarding** credentials and non-secret IDs,
shared across **every module** (members / events / webshop …) and **every plane** a module
touches (SAM/DynamoDB, Flask/MySQL, Cognito). This is the single, tenant-owned home for
onboarding material so a credential's ownership is always obvious from its path.

> **Onboarding-only — NOT production.** These credentials exist to run one-off (and possibly
> long-running) onboarding/migration tasks. Production secrets have a separate, encrypted
> solution in MySQL. Do not treat this folder as the production secret store.

Spec: `.kiro/specs/Common/Tenant/tenant-onboarding-tooling/`.

## Layout

```
scripts/tenants/
  README.md                     # this file (committed)
  <tenant>/                     # e.g. h-dcn/
    secrets.example.json        # committed — non-secret TEMPLATE (copy it, don't edit in place)
    secrets.local.json          # git-ignored — your real IDs + the credentials map
    <credential>.json           # git-ignored — the real credential file, CO-LOCATED here
```

## Git policy (fail-closed)

Everything under a tenant dir is **git-ignored by default**; only the committed template(s)
and READMEs are un-ignored (see the repo-root `.gitignore`). So any credential file you drop
in — whatever its name — is ignored automatically. To commit a genuinely non-secret file, add
an explicit un-ignore line on purpose.

## The two files

- **`secrets.example.json`** (committed) — the shape, with placeholders. Never real values.
- **`secrets.local.json`** (ignored) — your copy with real values. Create it with:

  ```bash
  cp scripts/tenants/<tenant>/secrets.example.json scripts/tenants/<tenant>/secrets.local.json
  # then edit secrets.local.json and drop the real credential file beside it
  ```

## Credentials map (keyed by purpose)

Credentials are a **named map keyed by purpose**, so a tenant can carry more than one. Each
file-based entry names a credential file that lives **beside** `secrets.local.json` in the same
tenant dir:

```jsonc
{
  "credentials": {
    "google_sheets": { "type": "google_service_account", "file": "google-service-account.json" }
    // add more purposes as needed, same shape
  },
  "sheet_id": "…",
  "worksheet": "Ledenbestand",
  "folder_ids": { "facturen": "…" }
}
```

A runner asks for a credential **by purpose** (e.g. `google_sheets`); the resolver
(`scripts/onboarding/_lib/tenant_resolver.py`) turns `credentials.<purpose>.file` into the absolute
path of the co-located file. An explicit `--credentials <path>` CLI flag overrides it. A
missing purpose/key fails loudly — there is no silent default.

> Phase 1 wires only **file-based** credentials. Other `type`s (API token, SSH key, …) follow
> the same declarative shape and are wired when a tenant first needs them.
