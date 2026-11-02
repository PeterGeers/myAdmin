# Task 9.4 — Live end-to-end on TEST (OWNER-RUN runbook)

> **OWNER-RUN.** This document is the step-by-step runbook the OWNER executes to verify Task 9.4
> live. It was AUTHORED (not executed) by the task agent — no live e2e was performed, no mutating
> AWS call was made, no publish happened, and Task 9.4 is **NOT** marked complete. The agent's job
> was to write this; the owner runs it and ticks 9.4 only after the PASS checklist (bottom) is
> green.
>
> **Requirements proven here:** R3.1, R5.1, R5.4, R5.5, R6.2, R6.3, R10.7, R10.8.
>
> **⛔ Environment: TEST only** (steering 43 — the branch is the env selector; this verifies the
> `test`-branch deployment, not production). Use a **disposable** tenant/slug and CLEAN UP (§8).

## Concrete values this runbook uses (mined from spec / findings / code — confirm before you run)

| Thing | Value | Source |
| --- | --- | --- |
| Public-pages bucket (nonprofit) | `myadmin-public-pages-nonprofit-506221081911` | hosting findings 6.2 |
| CloudFront distribution (`*.jabaki.nl`) | `E3GLUX3TWBIJG` (nonprofit acct `506221081911`) | hosting findings 6.2 |
| Served artifact keys | `{slug}/index.html` + `{slug}/form.json` | `public_page_artifact_store.py` |
| Control-plane slug marker | `_slugs/{slug}` (body `{owner_plane,kind,tenant_id,resource_ref}`) | `slug_marker_store.py` / design D-SLUG |
| Authenticated publish route | `POST /members/application-form/publish` (`members:admin`) | `application_publish.py` |
| Public read route | `GET /public/members/{slug}/field-config` (no auth) | `handler/public_app.py` |
| Public submit route | `POST /public/members/{slug}/applications` (no auth) | `handler/public_app.py` |
| Embed-origins KVS | `myadmin-application-embed-origins` (CSP `frame-ancestors`) | `infrastructure/application-form.tf` |
| Embed origins authored on | `config#mail` attr `application_embed_origins` via `PUT /members/config/mail` | `config_write_service._shape_embed_origins` |
| Nonprofit AWS profile | `nonprofit-deploy`, acct `506221081911`, region `eu-west-1` | steering 23/41 |

> Prefer pulling the TEST public host, the SPA base URL, the authenticated/public API invoke URLs,
> and the applications table name from `samconfig.toml [test]` / the TEST stack outputs / your
> running TEST frontend — do **not** guess them. Where a command below has `{...}`, substitute the
> real TEST value first.

## Shell preamble (steering 41 — WSL, judge success by the in-band marker, not the tool exit code)

Every command: inline POSIX `cd`, append the success marker, strip stray AWS creds so the profile
resolves to the RIGHT account. All `aws` here is **read-only** (`ls`, `get-item`,
`get-key-value`, `sts`) — nothing mutating.

```bash
# strip helper + nonprofit profile (the override-ranking trap — 41)
STRIP='env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN -u AWS_ENDPOINT_URL_DYNAMODB'
P='--profile nonprofit-deploy --region eu-west-1 --output json'
# success marker — marker=0 means OK; the tool's own "Exit Code: -1" is ALWAYS reported, ignore it
run(){ cd /home/peter/projects/myAdmin && eval "$@"; printf '\n<<<DONE marker=%s>>>\n' "$?"; }
```

---

## §1 — PRECONDITIONS (confirm ALL before touching anything)

1. **TEST environment.** You are verifying the `test`-branch deployment (stacks `test-sam-members`,
   `test-pretokengen`), not prod. Frontend TEST is the local dev server (`VITE_APP_ENV=test`,
   `localhost:3000`) — there is no hosted TEST SPA (steering 43).
2. **Code deployed.** SAM Members (Tasks 8.1 publish-claims-slug + 9.1 live write) and the Railway
   backend are deployed with current `test` code; the public `MembersPublicApi` routes
   (`field-config` / `applications`) are live.
3. **Nonprofit hosting live.** The hosting migration
   (`.kiro/specs/myBacklog/jabaki-hosting-migration-to-nonprofit`) is COMPLETE: bucket
   `myadmin-public-pages-nonprofit-506221081911` + distribution `E3GLUX3TWBIJG` own `*.jabaki.nl`,
   and a disposable test tenant was already publish-verified-200 into that bucket (findings 6.2).
4. **Identity check — MUST print `506221081911` (NonprofitDeployRole), NOT `344561557829`:**

   ```bash
   run "$STRIP aws sts get-caller-identity $P"
   # expect: "Account": "506221081911" and an ...assumed-role/NonprofitDeployRole/... ARN
   ```

   If it prints `344561557829`, STOP — a stray static key is winning over the profile
   (steering 41 override-ranking trap). The `$STRIP` prefix above is the fix; do not proceed until
   the identity is nonprofit.
5. **⚠ OWNER-RUN 9.2 IAM follow-ups — know the state BEFORE you interpret §3/§4 results.** Two
   IAM items from Task 9.2 are owner-run and MAY still be open (findings 6.2 "STILL OPEN"):
   - the **prefix-scoped publish policy** (SEC-8 — `s3:PutObject/DeleteObject` scoped to `{slug}/*`
     + the `_slugs/{slug}` markers), and
   - the **cross-account CloudFront invalidation** path (role/ARN in nonprofit).

   **Without them, invalidation is DENIED and NON-FATAL** (by design — `public_page_artifact_store
   ._invalidate` logs + swallows). Consequence you must expect: a **NEW** page appears immediately;
   an **UPDATE** to an existing page is **TTL-delayed** (≤ ~1h, default 5 min). So §3–§5 use a
   **brand-new** disposable slug (immediate), and if you ever re-publish the same slug, wait out the
   TTL or treat staleness as expected, not a failure.

**Expected:** all five confirmed; identity = `506221081911`; you know whether invalidation is live
or deferred.

---

## §2 — AUTHOR A SLUG (make a disposable TEST tenant publish-ready)

The publish **readiness gate** (`application_publish._require_ready`) refuses unless THREE
preconditions hold — author all three on your disposable TEST tenant, in the SPA (members:admin),
or via the config APIs:

1. **A stored slug** on `config#fields` that satisfies format + the SEC-4 prefix rule: it must be
   `{prefix}` or `{prefix}-{suffix}` under the AUTHENTICATED tenant's own `public_prefix`
   (Task 6.3). Pick a disposable one, e.g. `{prefix}-e2e94`.
2. **A certified sender** — `mail_certified` true + a projected `mail_domain` (the `is_send_ready`
   predicate). Without it the gate returns `no_certified_sender`.
3. **≥1 on-form field** — at least one field marked `application_visible` (the gate counts the
   `get_public_field_config` → `fields` list). Without it → `no_on_form_field`.

**Expected:** the SPA Publish button is ENABLED (no "why disabled" hint), i.e. all three
preconditions are satisfied for the disposable tenant. If disabled, the hint names the first
missing precondition — fix it and recheck.

---

## §3 — PUBLISH (authenticated `members:admin`)

Publish via the SPA Publish button, OR by curl with a members:admin bearer token:

```bash
# {AUTH_API} = authenticated members API invoke URL (TEST); {TOKEN} = a members:admin JWT
run "curl -s -X POST '{AUTH_API}/members/application-form/publish' \
  -H 'Authorization: Bearer {TOKEN}' -H 'Content-Type: application/json' | tee /dev/stderr"
```

**Expected:** HTTP 200 with body shaped
`{\"success\": true, \"slug\": \"{prefix}-e2e94\", \"published_version\": <n>, \"published_at\": \"<iso>\"}`.
(On a not-ready tenant you'd get a 409 `publishNotReady`; a foreign slug → 409 `publishSlugConflict`;
a bad slug → 422 `publishSlugRejected` — none of those is the success case.)

**Read-only confirm the served artifacts landed** (two keys under the slug prefix):

```bash
run "$STRIP aws s3 ls 's3://myadmin-public-pages-nonprofit-506221081911/{prefix}-e2e94/' $P"
# expect two lines: index.html  and  form.json
```

> If the Railway publish log shows a CloudFront invalidation WARNING, that is the known-deferred
> 9.2 gap (§1.5) — NON-FATAL. The `put_object` is authoritative; the page is published.

**Expected:** 200 success envelope + `s3 ls` shows `index.html` and `form.json`. Proves **R3.1**
(a published page = rendered `{slug}/index.html` + `{slug}/form.json` + claimed slug marker).

---

## §4 — SERVE (load the public page over `*.jabaki.nl`)

1. **Browser:** open `https://{prefix}-e2e94.jabaki.nl/` — the thin shell renders and (per Task 5)
   client-side fetches the schema and draws the form via `ApplicationFormRenderer`.
2. **Artifact serves (read-only HEAD):**

   ```bash
   run "curl -sI 'https://{prefix}-e2e94.jabaki.nl/'"
   # expect: HTTP/2 200  and  content-type: text/html; charset=utf-8
   ```

3. **Field-config returns the whitelisted schema (no auth):**

   ```bash
   # {PUBLIC_API} = the MembersPublicApi invoke URL / the *.jabaki.nl-fronted public path
   run "curl -s 'https://{prefix}-e2e94.jabaki.nl/public/members/{prefix}-e2e94/field-config' | tee /dev/stderr"
   # expect: 200 JSON whose 'fields' is the applicant allow-list ONLY — NO overrides / field_overlay /
   #         credentials / internal config leak (SEC-1 fail-closed)
   ```

**Expected:** page renders in the browser; `curl -I` → 200 `text/html`; field-config → 200 with the
whitelisted applicant schema and nothing un-whitelisted. Proves **R5.1** (public no-auth
`GET {slug}` schema), **R5.4** (published shell fetches + renders via `ApplicationFormRenderer`).

---

## §5 — CUSTOM DOMAIN URL-PRESERVED (no redirect)

For a tenant custom domain attached to this page (via `tenant_custom_domains` + ACM +
CloudFront-alias + the `domain_mapping` KVS), confirm the content serves WITHOUT a 30x redirect —
the custom domain stays in the address bar:

```bash
# {CUSTOM_DOMAIN} = the tenant-owned host CNAMEd to the distribution
run "curl -sIL 'https://{CUSTOM_DOMAIN}/' | grep -Ei '^(HTTP/|location:)'"
# expect: a SINGLE  HTTP/2 200  line, NO  3xx  hop and NO  location:  header pointing at *.jabaki.nl
```

**Expected:** no 30x redirect hop in the `-IL` chain; the custom domain serves the page content
directly (URL preserved). Proves **R6.2**.

> If no TEST custom domain is wired, record that R6.2 is verified on the shared mechanism
> (`domain_mapping` KVS + the url-rewrite function already serve CNAME-without-redirect per the
> spec Context) and defer the per-domain live check — do NOT skip it silently.

---

## §6 — SUBMIT (tenant resolved from the MARKER, lands in the members store)

1. **Submit from the served form** (browser) OR by curl (no auth):

   ```bash
   run "curl -s -X POST 'https://{prefix}-e2e94.jabaki.nl/public/members/{prefix}-e2e94/applications' \
     -H 'Content-Type: application/json' \
     -d '{\"email\":\"e2e-applicant@example.com\", <...the published on-form fields...>}' | tee /dev/stderr"
   # expect: a success envelope (application accepted). A forged body 'tenant_id' is STRIPPED by the
   #         service and the marker-resolved tenant is stamped (SEC-3) — never trusted from the body.
   ```

2. **The tenant is resolved FROM THE `_slugs/{slug}` MARKER BODY, not the slug string** — the edge
   does an O(1) `get_object` on `_slugs/{prefix}-e2e94` and routes on its `owner_plane`/`kind`
   (`sam` / `application_form`). You can read that marker read-only to confirm the resolved tenant:

   ```bash
   run "$STRIP aws s3 cp 's3://myadmin-public-pages-nonprofit-506221081911/_slugs/{prefix}-e2e94' - $P"
   # expect body JSON: {\"owner_plane\":\"sam\",\"kind\":\"application_form\",\"tenant_id\":\"{TENANT}\",\"resource_ref\":\"config#fields\"}
   ```

3. **The record LANDED under the resolved `tenant_id` in the members store** — read-only check on
   the TEST applications table (nonprofit account, strip-and-verify profile; substitute the real
   TEST table name + the `tenant_id`-partitioned key shape from the SAM template / repository):

   ```bash
   run "$STRIP aws dynamodb query --table-name {TEST_APPLICATIONS_TABLE} \
     --key-condition-expression 'tenant_id = :t' \
     --expression-attribute-values '{\":t\":{\"S\":\"{TENANT}\"}}' $P \
     --query 'Items[?status.S==\`application\`]'"
   # expect: at least one item for the resolved tenant with status = 'application' (the new submit)
   ```

**Expected:** submit returns success; the marker body names the resolving tenant (not the slug
string); a `status=application` record exists under THAT `tenant_id`. Proves **R5.5** (submit
resolves tenant as data + writes into the members module's own `tenant_id`-partitioned store) and
**R6.3**'s sibling tenant-isolation via the marker.

---

## §7 — CSP `frame-ancestors` SEC-7 (deny-by-default, then explicit allow)

The viewer-response function `application_form_frame_ancestors` (`infrastructure/application-form.tf`)
reads the `myadmin-application-embed-origins` KVS keyed by the FORM HOST and emits the CSP header
**only** on the explicit-allow path; missing/empty = NO header = not embeddable (`'none'`).

1. **No `application_embed_origins` entry for this host → NO header (default closed):**

   ```bash
   run "curl -sI 'https://{prefix}-e2e94.jabaki.nl/' | grep -i 'content-security-policy' || echo 'NO CSP header (= frame-ancestors none, not embeddable)'"
   # expect: NO 'content-security-policy: frame-ancestors' header → prints the fallback line
   ```

2. **Author an allowed origin**, then re-check. Author it on `config#mail` (input-validated by
   `_shape_embed_origins` — https-only, no `*`, no injection; Task 9.3) so the backend populates the
   KVS entry for the form host:

   ```bash
   run "curl -s -X PUT '{AUTH_API}/members/config/mail' \
     -H 'Authorization: Bearer {TOKEN}' -H 'Content-Type: application/json' \
     -d '{\"application_embed_origins\":[\"https://sites.google.com\"]}' | tee /dev/stderr"
   # then (allow KVS propagation) re-HEAD the page:
   run "curl -sI 'https://{prefix}-e2e94.jabaki.nl/' | grep -i 'content-security-policy'"
   # expect: content-security-policy: frame-ancestors https://sites.google.com
   ```

   > **Caveat:** CloudFront KVS updates propagate on a TTL — the header may lag a few minutes after
   > the write. Re-run the HEAD until it appears; a short lag is propagation, not a failure.

**Expected:** no entry → no `frame-ancestors` header (`'none'`, not embeddable); after authoring an
allowed origin → the header appears carrying exactly that origin. Proves **R6.3** / **R10.7** /
**R10.8** (framing defaults closed; tenant-authored origin applied; input-validated on write).

---

## §8 — CLEANUP (leave NO residue from the disposable slug)

Remove everything the e2e created. These ARE mutating — the owner runs them deliberately at the end:

1. **Delete the served artifacts** under the slug prefix:
   ```bash
   run "$STRIP aws s3 rm 's3://myadmin-public-pages-nonprofit-506221081911/{prefix}-e2e94/' --recursive $P"
   ```
2. **Delete the slug marker** `_slugs/{prefix}-e2e94` (release the claim):
   ```bash
   run "$STRIP aws s3 rm 's3://myadmin-public-pages-nonprofit-506221081911/_slugs/{prefix}-e2e94' $P"
   ```
3. **Delete the test applicant record** from `{TEST_APPLICATIONS_TABLE}` (the `status=application`
   item the §6 query returned — delete by its full key).
4. **Remove the embed-origins entry** authored in §7: `PUT /members/config/mail` with
   `application_embed_origins: []` (clears both the KVS entry and the CORS list — one write, two
   enforcers).
5. **Decommission the disposable tenant / its slug on `config#fields`** if it was created solely for
   this run.

**Expected:** `aws s3 ls .../{prefix}-e2e94/` and `s3 ls .../_slugs/{prefix}-e2e94` both return
nothing; the applicant record is gone; the page no longer serves; no embed-origins entry remains.

---

## PASS criteria — requirement → the step that proves it

| Requirement | Proven by | Pass condition |
| --- | --- | --- |
| **R3.1** — published page = rendered `{slug}/index.html` + `{slug}/form.json` + claimed slug marker | §3 | 200 publish envelope; `s3 ls` shows both artifacts; `_slugs/{slug}` marker present (§6.2) |
| **R5.1** — public no-auth `GET {slug}` returns applicant schema | §4.3 | field-config → 200 whitelisted schema, no auth |
| **R5.4** — published shell fetches + renders via `ApplicationFormRenderer` | §4.1 / §4.2 | page renders in browser; `curl -I` → 200 `text/html` |
| **R5.5** — submit resolves tenant as data, writes to members `tenant_id` store | §6 | submit success; `status=application` record under resolved `tenant_id` |
| **R6.2** — custom domain serves URL-preserved (no redirect) | §5 | `curl -IL` → single 200, no 3xx / `location:` hop |
| **R6.3** — CSP `frame-ancestors` from `application_embed_origins`, else `'none'` | §7 | no entry → no header; allowed origin → header = that origin |
| **R10.7** — framing defaults closed; origins input-validated on write | §7 (+ Task 9.3 record) | no-entry host not embeddable; `_shape_embed_origins` rejects `*`/injection |
| **R10.8** — least-privilege prefix-scoped publish IAM | §1.5 / §3 | publish writes ONLY `{slug}/*` + its `_slugs/{slug}`; identity = `506221081911` |

All eight rows green → Task 9.4 passes. Then (and only then) the owner marks 9.4 complete.

## ROLLBACK

Everything in §1–§7 is either read-only or scoped to the ONE disposable slug, so rollback is
exactly §8 (delete the slug's artifacts + marker + the test applicant record + the embed-origins
entry). The e2e touches NO other tenant's pages and performs NO infra change (no `sam deploy`, no
`terraform apply`) — so there is nothing stack-level to revert. If a publish half-completed (e.g.
marker claimed but artifacts missing), §8.1 + §8.2 still fully clean it. If an UPDATE looked stale,
that is the known-deferred invalidation gap (§1.5), not a change needing rollback — it self-heals at
the cache TTL.
```