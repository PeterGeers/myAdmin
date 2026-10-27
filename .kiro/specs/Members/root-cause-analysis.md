# Root-Cause Analysis — the Members config / application-form saga

> Written 2026-10-23. Based on **git history and filesystem timestamps**, not memory. Every date
> below is a real commit date (`git log`) unless marked as a filesystem mtime. The goal is to
> explain *why we are where we are* and what to change — not to assign blame. The evidence says the
> judgment was sound; the **process and pace** are what broke.

---

## TL;DR

One bug class — **"read/write source mismatch"**: a config surface writes to the authoritative
store (SAM `config#*`) but reads back from a *different* source or a *recomputed* identity, so after
a correct save the UI shows stale/blank/empty state and the tenant admin "loses control."

It was **correctly diagnosed on 2026-10-21** (spec 02 Mail findings) with the correct fix stated:
*load from the same place you write; writer and reader share one shape so they cannot drift.*

Then, over the next **~48 hours**, three more specs were built on top at high speed. The one
**structural** fix that generalizes the Oct-21 lesson — *the server owns storage placement so the
frontend never reconstructs the key* (spec 11 "decision B") — was **explicitly deferred** in spec
12. So the same bug class re-appeared in the field builder and in field-config itself. The current
`findings.md` ("lost control") is that same class, third occurrence.

### Branch reality (verified `git branch -r --contains`, 2026-10-23)

This was checked, not assumed. The promotion picture is **split**, and the split is the key to
reading the risk correctly:

| Layer | On `origin/main` (production)? | Evidence |
|---|---|---|
| Spec 02 — SAM-owned write path + `overlayModel` engine | **YES, in production** | `ca2eba259`, `00f176d1a` contained in `origin/main` |
| Spec 02 — Mail "read back from authoritative source" fix | **YES, in production** | `f590951d6` contained in `origin/main` |
| members-overview-tweaks | **YES, in production** | merged `048f9779a` (PR #155), 2026-10-21 |
| Spec 11 — early builder + the 3 round-trip patches | **YES, in production** | `60fbc922f`, `7f99bbc73`, `8b287229f`, `a67d85c07`, `112d14955` all contained in `origin/main` |
| **Spec 12 — the field-modal authoring UI** (`ApplicationFieldModal.tsx`, `applicationChoiceSource.ts`) | **NO — not on `main` OR `test`; uncommitted working-tree only** | absent from `git ls-tree origin/main`; spec-12 folder has zero commits |

So the accurate statement is NOT "the recent work was held on `test`, not `main`." It is more
specific and more important:

- **The foundation and the early builder round-trip (spec 02 + spec 11) WERE promoted to
  production** — including the symptom patches (`seed overlay`, `merge writes`, `one-key
  contract`). Those were not pre-merge hardening on `test`; they were patches on a bug class that
  was **already live in `main`**.
- **The spec-12 field-modal rewrite — the surface where "lost control" is being tested right now —
  was correctly NOT promoted.** It is uncommitted local work sitting on top of the production
  foundation. The instinct *"test wasn't solid enough to push to main"* is RIGHT about spec 12: it
  never got committed, let alone merged. Holding it back was the correct call.

**Why this matters for root cause:** the gate that should have caught the read-back bug was the PR
into `main` for spec 11 — and it didn't, because nothing in that verification exercised a
previously-saved field against real data. The bug reached production through a reviewed merge, then
got patched three times *in production*. The spec-12 modal work being held in the working tree is
the system working as intended (don't promote the unsolid rewrite); the spec-11 round-trip reaching
`main` unverified is the system failing. See process root cause #5.

**The problem is not the diagnoses. It is that the correct fix kept being deferred to keep moving,
and each new spec was layered on an unverified foundation.**

---

## The real timeline (git commit dates, not folder numbers)

> IMPORTANT: the folder numbers (01, 02, 10, 11, 12) are **misleading**. They were assigned in a
> single bulk commit on 2026-10-20 (`c9c11afbf / 3a5c42781 / d2be09f41`,
> *"docs(specs): reorganize .kiro/specs Members into numbered structure"*). The numbering is a
> post-hoc filing system, NOT the build order. The build order is in the **code** commits below.

| When (real) | Commit / fact | What happened | Scope |
|---|---|---|---|
| **2026-09-28** | `d3ba5d8e6` (first commit touching the tree) | The whole `Common/Serverless-applications` SAM foundation lands (multi-tenant s1–s5f, JWT toolkit, projection table, edge). | SAM plane groundwork. **3+ weeks before** the Members config work. |
| **2026-10-20 00:54** | `88240663a` | "Members SAM redesign analysis" committed alongside CodeQL work. | The redesign thinking begins. |
| **2026-10-20 16:50 → 23:55** | `ca2eba259` … `d18670893` (PR #142) | **Spec 02 built in a single evening**: SAM-owned config write path, `config#fields` cutover, scope derivation, mail validator, `mail_reply_to_default`. ~8 commits in ~7 hours, including mid-flight data-loss fixes (`64b9b44b5`, `a16aa4ff4`). | DynamoDB becomes system-of-record for `config#fields/scope/mail`. Large, foundational. |
| **2026-10-21 00:06 → 11:17** | `486f26802` … `ad36e99a6` | Spec 02 finished: ProjectionSync builders removed, **typed Mail function**, and `f590951d6` *"Read config#mail back from the authoritative SAM source (fix mail save not sticking)"*. | **This is the first occurrence of the bug class AND its correct fix.** |
| **2026-10-21 11:24** (mtime) | `02/findings.md` | The Mail findings doc records the diagnosis verbatim: *"read/write source mismatch (NOT a save failure)… the form must LOAD from the same place it WRITES… writer and reader share the shape so they cannot drift."* | **The lesson is now written down.** |
| **2026-10-21 17:43** | `1b87c738e` | **members-overview-tweaks** shipped (controls above table, edit/view field partition, responsive modals, tenant-prefixed export naming, inbox relocation). A separate, small, well-scoped spec — notably the ONE that has NOT come back with findings. | Frontend presentation + export naming. Small, independent. |
| **2026-10-21 20:36 → 23:15** | `60fbc922f`, `5a6cd294c`, `7f99bbc73`, `8b287229f`, `a67d85c07` | **Spec 11 (application form builder) built the same evening**, including four rapid round-trip fixes: *serve per-field attrs*, *seed overlay from SAM row*, *merge writes onto stored row (stop partial saves wiping it)*, *one-key contract for overrides*. The commit subjects themselves are the bug class recurring and being patched incrementally. | The authoring UI on top of `config#fields`. |
| **2026-10-22 18:08–22:18** (mtime) | `11/requirements,design,tasks,findings` | Spec 11 formalized as docs after the code; findings recorded more breakage. | — |
| **2026-10-22 20:51** | `112d14955` | Spec 11 code round 2: native landing-page block + authoring UI. | — |
| **2026-10-23 14:56** (mtime) | `11/redesign.md` | The redesign notes: **verifies the round-trip was fine with real data**, and names **decision B** (server owns placement, frontend stops constructing the overlay shape) as the structural fix. | The correct generalization of the Oct-21 lesson, written down a second time. |
| **2026-10-23 16:57 → 20:13** (mtime) | `12/*` | **Spec 12 authored.** Adopts A (modal UX) + C (serving/publish redesign). **Defers B** — tasks.md "Parked": *"Server-owned overlay storage placement — deferred; the builder reuses `upsertField`."* **Spec 12 has ZERO git commits — it is uncommitted working-tree only, never a reviewed/tracked spec.** | Serving/publish redesign (slugs, S3, CloudFront, IAM). Large infra scope; the authoring seam treated as "reuse." |
| **2026-10-23 22:05** (mtime) | `12/findings.md` | **Today.** "The functional group flow is completely missed… toggle on previously-saved fields doesn't work… field configuration shows empty groups, labels gone… lost control." Plus a backend `ClientError` ("Tenant user request failed"). | The bug class, third occurrence — now also hitting field-config, not just the builder. |

### Two facts the folder numbers hid

1. **Spec 12 was never committed.** `git log` for its folder returns nothing. It is an uncommitted
   plan in the working tree. So "tasks marked `[x]`" in spec 12 reflect work tracked *only* in that
   uncommitted file — there is no reviewed trail that the authoring phases were verified.
2. **`findings.md` files were deliberately gitignored on 2026-10-20 18:41** (`41bbc5f82`,
   *"stop tracking per-spec findings.md scratchpads, gitignore them"*). That means the **most
   important evidence trail — the bug findings — stopped being version-controlled right at the
   start of this saga.** The Oct-21 Mail diagnosis and the Oct-23 "lost control" report are not in
   git history. Losing that trail is part of why the lesson didn't carry forward.

### The commit ratio tells the story

In the Members config/builder code, **2026-10-20 → 10-23: 6 `feat` commits vs 8 `fix` commits.**
More fixes than features, and the fix subjects are the same round-trip problem restated
(*"stop partial saves wiping it"*, *"seed overlay from SAM row"*, *"one-key contract"*,
*"read config#mail back from the authoritative source"*). That is the signature of **patching a
symptom repeatedly instead of removing its cause once.**

---

## Root cause

### The technical root cause (one sentence)

**Config authoring was migrated to a SAM-owned write store (`config#*` on DynamoDB) correctly, but
the frontend read-back was never unified to a single authoritative source + stable field identity —
so each surface that reads config back either reads the wrong source (Mail → MySQL) or reconstructs
the storage key on the client (`resolveWriteTarget` → `{group}.{key}`), and drifts from what was
written.**

The fix for this is architectural and was identified twice:
- Spec 02 (Mail): *read back from the same authoritative source you write to.*
- Spec 11 (builder, "decision B"): *let the server own storage placement so the frontend never
  constructs the overlay key.*

Both are the same principle. Neither was generalized into a rule applied everywhere. Spec 12
**deferred** the builder half of it.

### The process root causes (why the technical fix didn't stick)

1. **Specs were written AFTER the code, as filing, not as design gates.** The numbered folders were
   a bulk reorg on Oct 20; spec 11's docs (Oct 22) post-date its code (Oct 21); spec 12 was never
   committed at all. A spec that is written after the code — or never committed — cannot function as
   a design review that catches "you're about to reintroduce the Oct-21 bug." It becomes a
   description of what was already built.

2. **The lesson was recorded in a file that is gitignored.** The one artifact that captured the root
   cause (`findings.md`) was explicitly removed from version control at the start of the saga. So
   when the next spec started, the lesson was in an untracked scratchpad, not in a reviewed spec
   requirement or a steering rule. It could not travel forward.

3. **Pace outran verification.** Spec 02 (a foundational system-of-record migration) was built in a
   single evening; spec 11 in the next evening; spec 12's plan the day after. There was no pause to
   verify the previous foundation end-to-end against **real tenant data** before building the next
   layer on it. The redesign notes even admit nearly "fixing the wrong thing twice" because of a bad
   test fixture — a direct symptom of inference-over-verification under time pressure.

4. **The structural fix was repeatedly deferred to keep shipping.** Decision B was known and named.
   It was parked in spec 12 as "out of scope" precisely because doing it properly (server owns
   placement) is more work than "reuse `upsertField`." Deferring the one fix that removes the bug
   class, in favor of the cosmetic/infra half, is why the saga didn't end.

5. **"Done" was defined by tasks checked off, not by live verification of the broken thing.** Spec
   12's only end-to-end verify targets the *serving* path (publish → load → submit). Nothing in the
   plan says "open the builder for a tenant with previously-saved fields and confirm toggles persist
   and groups render" — i.e. nothing exercised the exact thing that was broken. So it could be
   marked complete while completely broken.

---

## What was actually fine (so we don't thrash the wrong layer)

Spec 11's redesign notes **verified with real data** that:
- the stored `config#fields` row for `h-dcn` is correct (right dotted override keys, flags set);
- the SAM reader + resolver + `get_public_field_config` return the right fields from that row;
- the frontend write path produces a clean overlay **once the test fixture uses the real server key
  shape (bare `key` + separate `group`)**.

So: **the backend store, the reader, and the write are not the problem.** The problem is the
frontend **read-back identity** (recomputed `{group}.{key}` vs. the key the field was saved under)
and, for Mail, the **read-back source** (MySQL vs SAM). Do not rewrite the SAM plane.

(Separately, today's backend `ClientError` — "Tenant user request failed" from
`tenant_admin_users.py` on a Cognito call — is a *different* issue, almost certainly environment/
identity, to be chased via the logged `error_id`. It is not part of this config bug class.)

---

## Recommendation — stop the saga, don't start spec 13 the same way

### Technical (the actual fix)

**Finish decision B / generalize the Oct-21 rule. One of two, smallest-first:**

- **Minimum viable (frontend-only):** give the overlay model a **single stable field identity** so
  read and write always agree regardless of `group`/`functional_group` drift. Match a saved base
  field by the identity it was *stored under* (fall back across dotted/bare on BOTH read and write,
  or normalize once on load), so `toggleOnForm`/`toggleChoice` edit the existing entry instead of
  creating an orphan. Add a regression test that loads the **real `h-dcn` row**, toggles a
  previously-saved field, and asserts it flips (not a hand-built fixture — the redesign notes warn a
  wrong fixture hid the truth once).
- **Proper (the structural end-state):** move storage placement to the server — the frontend writes
  by field identity, the server decides `fields` vs `fixed_overrides`. This removes the client-side
  key reconstruction permanently and is what spec 02's requirements already describe ("one typed
  door", "writer and reader cannot drift").

**Make the read/write-parity rule a steering rule**, not a scratchpad note, so it cannot be deferred
again: *"A config surface MUST read back from the same authoritative source and the same identity it
writes to; the frontend MUST NOT reconstruct storage keys."*

### Process (so this doesn't recur)

These are the changes to how the work is run. They are small and they directly address the five
process root causes above.

1. **Write the spec (or at least its acceptance criteria) BEFORE the code, and commit it.** A spec
   that post-dates the code is documentation, not a gate. An uncommitted spec (like 12) is not a
   spec at all. If it's worth a folder, it's worth a commit.

2. **Stop gitignoring `findings.md`.** The findings ARE the institutional memory of what broke and
   why. Track them. Better: when a findings doc identifies a root cause, promote the fix into a
   **steering rule** or a spec **acceptance criterion** so the next spec inherits it automatically.

3. **One foundation per sitting, verified against real data before the next layer.** Do not build a
   system-of-record migration, an authoring UI, and a serving redesign in three consecutive
   evenings. After a foundational change, run it end-to-end against a real tenant (`h-dcn`) and
   confirm the *previously-broken* behavior, before stacking the next spec on it.

4. **Define "done" as "the broken thing is verified fixed against real data," not "tasks checked."**
   Every spec that touches a surface must have an acceptance criterion that exercises that exact
   surface with real data. "Publish works" is not evidence that "authoring works."

5. **Never defer the fix that removes the bug class in favor of the cosmetic/infra half.** When a
   structural fix (decision B) is known, do it first or not at all — shipping the easy half around a
   known-broken core is what turned one bug into a four-day, multi-spec saga.

6. **Collapse, don't accumulate.** Instead of spec 13, fold 02/11/12 into a single "Members config
   read/write parity" closure: apply the rule everywhere config is authored (fields, scope, mail),
   with real-data regression tests, and retire the superseded planning docs.

---

## The honest answer to "do I need to change my way of working?"

Yes — but **not your judgment.** The evidence is clear that you diagnosed the actual root cause
correctly on Oct 21, and named the correct structural fix. Twice. What needs to change is the
**operating rhythm around that judgment**:

- Slow the cadence so each foundation is verified before the next is built on it.
- Keep the findings trail in version control and convert findings into rules/criteria.
- Write-and-commit the spec before the code, and let it gate the build.
- Refuse to defer the bug-class fix in favor of the easy half.

You are not where you are because you can't trust yourself. You are here because a correct diagnosis
was out-run by a three-evening build cadence, and the one fix that would have ended it was parked to
keep shipping. Fix the cadence and the parking, and the judgment you already have does the rest.

---

# Addendum — TEST vs PROD evidence (2026-10-24, verified)

> Written so the findings below cannot be lost in a few clicks. Every statement here is backed by a
> `git diff`, a DynamoDB `get-item`, or a pytest run captured this session — not inference.

## The decisive reframing: it is DATA corruption on TEST, not broken configurator CODE

PROD's field configurator and user-tenant-roles work; TEST's do not. The instinct "the drift
happened after the last merge to main" is CORRECT, but the cause is NOT what we first assumed.

### Fact 1 — the field CONFIGURATOR code is IDENTICAL on main and test (verified)

`git diff --stat origin/main origin/test` over the configurator files shows **no change**:
`MembersFieldModal.tsx`, `overlayModel.ts`, `MembersConfigEditor.tsx`, `MembersFieldsTable.tsx`,
`MembersGroupModal.tsx` are byte-identical on both branches. Only the APPLICATION-FORM-BUILDER files
changed main→test (`ApplicationFieldModal.tsx`, `ApplicationField*`, `applicationChoiceSource.ts`,
`applicationPreviewFilter.ts`, `applicationShellForm.ts`, `index.ts`). `backend/src/routes/
tenant_admin_users.py` is ALSO unchanged main→test.

→ **The configurator being "broken" on TEST is NOT a code difference.** This OVERTURNS the earlier
loose claim that "the field configurator is broken." The configurator code is fine and unchanged.

### Fact 2 — TEST's `config#fields` DATA was corrupted by an application-form-builder save

Real `config#fields` rows, read live (read-only; both tables now have PITR + an on-demand backup):

| Attribute | PROD (`governance_projection`) | TEST (`test_governance_projection`) |
| --- | --- | --- |
| last write (`version`) | `2026-10-20T19:21` (pre-builder) | `2026-10-23T19:56` (during spec-12 work) |
| `overrides` count | 7 | 15 (8 new `personal.*`/`membership.*`) |
| overrides carrying `application_visible` | 0 | **12** (the builder's attribute) |
| tenant-field `functional_group` | **all intact** | **9 wiped to `None`** |

The 9 tenant fields whose `functional_group` is `None` on TEST but correct on PROD:

| tenant field | PROD group | TEST group |
| --- | --- | --- |
| build_year | `motor` | **None** |
| iban | `financial` | **None** |
| license_plate | `motor` | **None** |
| magazine_pref | `membership` | **None** |
| motor_brand | `motor` | **None** |
| motor_type | `motor` | **None** |
| newsletter_pref | `membership` | **None** |
| payment_method | `financial` | **None** |
| region | `membership` | **None** |
| additional_info / deregistration_date / notes / referral_source / termination_date | (group) | **same group (intact)** |

These 9 are EXACTLY the fields reported "missing from the application form" in
`12 - .../findings.md`, and exactly the 9 the real-data round-trip test
(`sam/tests/test_field_config_realdata_roundtrip.py`) orphans.

→ **A save through the APPLICATION FORM BUILDER on TEST (Oct 23, 19:56) rewrote the shared
`config#fields` row and dropped `functional_group` from the tenant fields it did not touch.** The
builder writes the whole overlay back; its overlay model did not preserve those fields'
`functional_group`, so the round-trip wiped them. PROD never received a builder save (the builder
was not used there), so PROD's data is intact. The two planes (configurator + builder) share ONE
`config#fields` row — so the builder's bad write corrupts the configurator's data. This is the
"the authoring surface can destroy the structure" risk, and it ALREADY HAPPENED on TEST.

### Fact 3 — the real-data round-trip test proves backend vs frontend split (verified, pytest)

`sam/tests/test_field_config_realdata_roundtrip.py` over the REAL h-dcn row:
- **PASS** — the resolver groups a BASE field (`gender`) under `personal` even though its stored
  override omits `functional_group` (base default). Server view is correct for base fields.
- **PASS** — on-form flags round-trip by identity (`email` on, `gender` off).
- **FAIL** — 9 TENANT fields orphan because their stored `functional_group` is `None` (the Fact-2
  corruption). The resolver's `_as_variable_field` falls back to the `overlay` group, which is not
  in the catalog → orphaned.

→ Two distinct problems, now cleanly separated:
1. **DATA corruption (TEST):** the 9 tenant fields lost their group via a builder save. PROD is the
   known-good copy.
2. **CODE bug (both planes):** (a) the frontend overlay tier buckets by the RAW stored
   `functional_group` instead of the RESOLVED one (orphans base fields whose override omits it);
   (b) the builder's write path does not PRESERVE `functional_group` on fields it doesn't touch,
   which is what caused the corruption. Fix = steering 39 / decision B: the backend owns placement,
   a write preserves untouched attributes, consumers use the resolved view.

## user-tenant-role failure — status: environmental hypothesis, NOT yet confirmed

- The route (`backend/src/routes/tenant_admin_users.py`) is **unchanged main→test** (verified `git
  diff`), so the failure is NOT a code regression on that path.
- The error "Tenant user request failed" is a boto3 `ClientError` from a **Cognito** call
  (`list_users` / `admin_get_user`) — an AWS/identity failure, surfaced with an `error_id`.
- It appeared in the SAME window as the AWS key rotation (`railway-breach-rotation`, 2026-10-23) and
  matches the override-ranking / wrong-account trap documented in steering 41.
- **UNCONFIRMED** — needs the server-side log line for `error_id e1c18f2390d44fd89548c0a170010adc`
  (it carries the exact AWS error code) and which env it was hit in (local dev vs Railway). Until
  that log line is read, this stays a hypothesis: likely environmental (credentials/account/expired
  token), NOT a code regression. Do not "fix" the code until the log confirms the cause.

## What to do (in safe order)

1. **Restore TEST `config#fields` from the known-good PROD copy** (or the PITR window / on-demand
   backup). A write to TEST — owner-approved. This un-corrupts TEST so the configurator can be
   tested against GOOD data, isolating the pure code bug from the data damage.
2. **Fix the builder write path (decision B / steering 39):** a save MUST preserve untouched
   attributes (`functional_group` et al.); the backend owns placement; consumers use the resolved
   view. Gate: `test_field_config_realdata_roundtrip.py` goes green.
3. **Confirm the user-tenant-role `ClientError`** from the `error_id` log line before touching that
   path; it is almost certainly environmental (key rotation / account), not code.

## Lesson for THIS file (process)

The analysis above was nearly lost because it lived only in chat. Findings that explain a
production-affecting difference MUST be written here (or in the relevant spec's findings) the moment
they are verified — not left in a conversation. "A few clicks and we are lost again" is itself a
root cause; this addendum is the countermeasure.

---

# RESOLVED — user-tenant-roles 500 on TEST (2026-10-24, fixed + verified)

> This supersedes the earlier "environmental hypothesis, NOT confirmed" note above. The cause is now
> confirmed from data and the fix is verified working.

## Symptom
`GET /api/tenant-admin/users` → HTTP 500 `{"error":"Tenant user request failed","error_id":...}` on
local TEST, while PROD worked fine. The envelope is the Flask `error_response` for an uncaught
`ClientError` (boto3) in `backend/src/routes/tenant_admin_users.py`.

## Root cause — a STALE `[default]` AWS profile after the key rotation (NOT code, NOT data)
- **No code changed** main→test (verified: zero `backend/src` diff; the whole user-tenant-roles
  chain — route, `sysadmin_helpers`, `admin_pool_resolver`, `cognito_utils`, `tenant_context`,
  `cognito_service`, `database` — is byte-identical on both branches).
- The backend runs in the **`backend` Docker container** (`docker-compose.yml`), which mounts
  `~/.aws:/root/.aws:ro` and **deliberately sets NO container-wide `AWS_PROFILE`** (compose comment:
  a container-wide profile would point Cognito at the wrong account — "user pool does not exist").
  DynamoDB uses a per-client `GOVERNANCE_PROJECTION_AWS_PROFILE=nonprofit-deploy`; **Cognito uses the
  DEFAULT credential chain** = the `~/.aws` `[default]` profile.
- Verified with `sts get-caller-identity`:
  - `[default]` → access key ending **`MM7P`** → `InvalidClientTokenId` (**DEAD**).
  - `[personal]` → access key ending **`C5MC`** → works (WebMaster, 344561557829).
  - `MM7P` is the breached `...XSLIMM7P` key **deleted during the railway-breach rotation**
    (2026-10-23). The rotation updated `[personal]` to the fresh `...C5MC` key but left `[default]`
    holding the revoked one.
- So the container's Cognito `list_users`/`admin_get_user` call authenticated with a revoked key →
  `ClientError` → the route's `except ClientError` → the 500. PROD was unaffected (Railway service
  variables carry valid creds).

## Fix (environmental — in `~/.aws`, not the repo)
Point `[default]` at the same working key as `[personal]`:
```bash
aws configure set aws_access_key_id     "$(aws configure get aws_access_key_id --profile personal)"
aws configure set aws_secret_access_key "$(aws configure get aws_secret_access_key --profile personal)"
# verify: must be WebMaster / 344561557829, no InvalidClientTokenId
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY aws sts get-caller-identity --region eu-west-1
```
Then `docker compose restart backend` (the container reads `~/.aws` read-only, so it needs a restart
to re-resolve the default). **Verified: user-tenant-roles works again after the restart.**

## Notes / wrong turns avoided
- A proposed fix of adding `AWS_PROFILE=personal` to `backend/.env` was **reverted** — the compose
  file deliberately keeps the container `AWS_PROFILE` UNSET (a container-wide profile breaks Cognito's
  pool resolution). The correct lever was the `[default]` profile content, not a new env var.
- This issue is INDEPENDENT of the field-config corruption and is NOT fixed by reverting code or
  restoring data. It is a local-workstation credential-rotation loose end.

## Lesson
When rotating an AWS key that multiple profiles share, update EVERY profile that used it — here
`[default]` was missed while `[personal]` was rotated, and the container's Cognito client reads
`[default]`. A rotation checklist should enumerate every `~/.aws` profile (and every service's
resolved profile) that referenced the retired key.

---

# ⚠️ THE PARTIAL-OVERLAY-OVERWRITES-FULL-RECORD BUG — 3 proven occurrences (2026-10-26)

> This is the SINGLE underlying defect behind the whole Members config saga, now proven THREE times
> against live data. Read this before touching the configurator or the application-form builder.

## The one defect (stated once)

`config#fields` is written as a WHOLE object (`PUT /members/config/fields` replaces the row). But the
frontend's working **overlay is a PARTIAL delta** — it contains only what the tenant has explicitly
authored. The platform BASE definitions (base functional groups, base field attributes like
`functional_group`, labels, choices) live in the server's **resolved** config, NOT in the overlay.

When a save writes the overlay back as if it were the complete record, **every base definition absent
from the overlay is DROPPED.** Read side and write side use different sources (resolved vs overlay),
so the write silently truncates the stored record to the partial overlay. This is the read/write
source mismatch from the top of this document, at the record level.

## Three proven occurrences (all live-data verified this cycle)

1. **Builder save stripped tenant-field attributes.** An application-form-builder save on TEST
   (2026-10-23) rewrote `config#fields` and dropped `functional_group` (+ `choices`, `label`, `type`,
   `options`) from 9 tenant fields. PROD (no builder save) stayed intact.
2. **`editGroup` silently no-op'd base-group edits.** Editing a base group's order/label did nothing
   (`if (idx < 0) return overlay`) because base groups aren't in the overlay — modal closed, no
   network, no save. (Patched: `editGroup` now materializes the base group. `overlayModel.ts`.)
3. **Group save truncated the `functional_groups` catalog.** 2026-10-26: a group edit+save on TEST
   rewrote `functional_groups` from 6 → 2 (`personal`, `address` only; the other 4 base groups
   dropped, surviving two even lost their labels). version stamp `2026-10-26T21:47`. fields/overrides
   stayed intact — ONLY the groups catalog truncated to the partial overlay.

Occurrences 1 and 3 are the SAME mechanism at two granularities (field attrs / group catalog).
Occurrence 2 is its silent-no-op cousin. Spot-patching 2 did not stop 3 — because the root (partial
overlay written as the full record) is unchanged.

## Live-data restores performed (TEST only; PROD is the known-good source; PITR + on-demand backup on)

- 9 tenant-field `functional_group` values restored from PROD (surgical).
- `functional_groups` catalog restored 6-from-PROD (2026-10-26), fields/overrides untouched, verified
  6 groups with labels + orders 10–60.

## 🚫 OPERATIONAL WARNING — until the fix is verified in the deployed TEST environment

**Do NOT edit + save a functional group (or author via the application-form builder) on TEST.** Any
such save re-truncates `config#fields` to the partial overlay and re-corrupts the data (this is how
occurrence 3 happened AFTER occurrences 1–2 were understood). The data is safe now; keep it that way
by not exercising the save until the fix is confirmed live.

> **Status (2026-10-27): the structural fix is BUILT and PROVEN GREEN — but only against local
> DynamoDB.** The server-side Change-Op write path (ADR
> [`0009`](../../docs/decisions/0009-config-fields-crud-change-op-server-owned.md); steering
> `39-backend-data-access-sam-dynamodb.md`) is implemented and the E2E invariant / truncation
> tripwire harness passes. Phases 2–8 of spec
> `03 - config-fields-foolproof-crud` are complete **except** the two deployed-environment checks:
> **8.6** (deployed-stage IAM smoke — local DynamoDB does not enforce IAM, so the
> `dynamodb:UpdateItem` grant is unexercised until it runs against the real TEST stack) and **9.1**
> (live TEST exercise: edit group order / add field / set choices against the deployed TEST stack,
> confirm no truncation and that the write persists across reload).
>
> **RETIRE THIS WARNING when — and only when — tasks 8.6 AND 9.1 confirm the fix in the deployed TEST
> environment.** Until that live confirmation exists, the local-only green run is NOT sufficient to
> clear the warning (the old defect only ever manifested against real data). Whoever runs 9.1: once
> it passes, delete this whole section and tick task 9.3's DoD item.

## The fix (structural — stop patching symptoms)

The save MUST NOT let the partial overlay overwrite base definitions. Two viable approaches:
1. **Preserve-on-write:** the write path merges the overlay onto the full resolved record, so base
   groups/attributes not explicitly overridden SURVIVE (never dropped because they're absent from the
   overlay). Server-owned placement (decision B / steering 39) is the clean home for this.
2. **Seed-full-on-load:** the editor seeds the working overlay with ALL resolved groups/fields on
   load, so "the overlay" always IS the complete set before any save.

This is the same decision as the owner's call that **application-form config must not live on
`config#fields`** (co-location is why a builder save can corrupt the core schema). Occurrence 3 is the
clinching evidence: the defect is structural, not a set of independent UI bugs. Next step is the
scoped structural fix, NOT a 4th spot patch.
