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
