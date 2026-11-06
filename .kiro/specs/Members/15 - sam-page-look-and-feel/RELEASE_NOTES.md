# Release Notes — Members 15 (SAM Page Look-and-Feel)

> Task 15 deliverable (CI/CD — quality gates, deploy paths, production-release gate; steering
> 40/43). This is the release/ops companion to the spec: the deploy-ordering invariant the
> change depends on, and the production-release gate for promoting it `test` → `main`.

## CI/CD coverage — verification evidence (no workflow change required)

The feature is already covered by the existing CI/CD. No workflow path-filter or test-glob edit
was needed; the evidence below was confirmed against the committed workflows and configs.

### Tests run in the Full Test Suite (`.github/workflows/full-test-suite.yml`)

`full-test-suite.yml` is the sole active lint/test gate (steering 43). It is the nightly cron +
`workflow_dispatch` (scope `all` / `backend` / `sam` / `frontend`).

- **SAM tests** — the `sam-tests` job runs a bare `pytest` from `sam/`, driven by `sam/pytest.ini`
  (`testpaths = tests`, `python_files = test_*.py`). Every new look-and-feel test under
  `sam/tests/` is therefore picked up automatically — no per-file registration:
  `test_page_styles*.py` (Layer-2 generator + Properties 1–5/7/8), `test_look_and_feel_*.py`
  (settings service, copy, dispatch, composition root, tenant isolation, invalid-value,
  carries-styling, publish-preserves-prior), `test_config_fields_look_and_feel_writer.py`, and
  `test_members_layer_packaging.py` (the task-2 build assertion).
- **Frontend tests** — the `frontend-tests` job runs `npx vitest run` with no path filter;
  vitest's `include` glob (`frontend/vite.config.ts`) is `src/**/*.{test,spec}.{ts,tsx}`, which
  picks up the preview Layer-2 mirror (`pageStyles.test.ts`) and the preview component test
  (`__tests__/ApplicationFormPreview.test.tsx`). The task-12 authoring-UI tests will be covered by
  the same glob once that (still-open) task lands — no config change needed.

Paired-test check at task-15 time: the SAM look-and-feel suite
(`test_members_layer_packaging`, `test_page_styles`, `test_look_and_feel_settings_service`,
`test_config_fields_look_and_feel_writer`, `test_look_and_feel_dispatch`,
`test_look_and_feel_composition_root`) ran green locally (93 passed, 0 failed).

### Deploy path filters already cover the changed paths (`.github/workflows/deploy-sam-members.yml`)

The Members deploy triggers on `push` to `main`/`test` with `paths: ["sam/members/**",
"sam/shared/**", ".github/workflows/deploy-sam-members.yml"]`. The feature's deployable changes
all fall inside those filters, so a merge deploys them on the branch→env contract (TEST on `test`,
PROD on `main`):

| Change | Path | Deploy filter matched |
| --- | --- | --- |
| Task 2 — layer packaging (remove Flask `cp`, ship `sam/shared/page_styles/`) | `sam/members/layer/Makefile` | `sam/members/**` |
| Task 1 — SAM-owned Layer-2 generator | `sam/shared/page_styles/` | `sam/shared/**` |
| Task 7.2 — renderer cutover (`branding=` wiring, `LookAndFeelSettingsReader`) | `sam/members/domain/application_publish.py`, `application_form_render.py` | `sam/members/**` |
| Tasks 4/5/8/9 — Layer-1 slice, service, routes, composition root | `sam/members/{repository,domain,handler}/` | `sam/members/**` |

**No new AWS resource is introduced.** The `look_and_feel` slice rides on the existing SAM-owned
`config#fields` row, which is already in the closed writable set `_WRITABLE_CONFIG_IDS` and uses
the existing version-conditional Change-Op `update_item` path — so the DynamoDB write needs **no
new IAM**. The published artifact reuses the existing public-pages publish path (spec 14). No new
table, bucket, queue, Lambda, or IAM statement is added by this feature. (If the task-12 authoring
routes ever need an egress beyond the existing `config#fields` write, that is a reviewed
allow-list addition to `scripts/check_sam_config_crud.py` — none is required today.)

### Infrastructure-as-Code (Terraform) — not touched by this feature

Steering 43 has a dedicated Terraform section (manual, plan-first apply workflow + an IaC
ordering rule) that must be evaluated for every release, even to record a N/A. For this feature
that evaluation is:

- **This feature changes no `infrastructure/*.tf`.** `git status -- infrastructure/` is clean; the
  feature adds no CloudFront, KeyValueStore, Cognito, S3, or IAM/Terraform resource. The
  look-and-feel capability stores presentation **values** on the SAM-owned
  `config#fields.look_and_feel` slice and generates CSS from them — all inside the existing SAM
  (CloudFormation) lifecycle, nothing in the Terraform lifecycle.
- **The application-form embed / `frame-ancestors` infra is NOT this feature's.** The CloudFront
  KeyValueStore (`myadmin-application-embed-origins`), the viewer-response function, and the backend
  IAM policy in `infrastructure/application-form.tf` already exist from the embed-origins work. They
  are fed by the tenant-authored `application_embed_origins` list on **`config#mail`** (via
  `PUT /members/config/mail`) — a different slice and a different spec. This feature's
  `config#fields.look_and_feel` slice never touches that KVS/function, so that infra is owned and
  deployed elsewhere and rides **no new apply** here.
- **Therefore the steering-43 Terraform plan-first manual-apply workflow and the "apply IaC first /
  in the same window" ordering rule DO NOT APPLY to this feature's release.** There is no `.tf`
  change to `terraform plan -out`/review-for-replacement/`apply`, and no IaC prerequisite that must
  precede the SAM/frontend deploy. This feature promotes through the SAM + frontend deploy paths
  only (above).

## Deploy-ordering invariant (MUST deploy together)

The task-2 layer-packaging change and the task-7.2 renderer cutover are a **single atomic
deploy** — they must land in the same deploy, and they do, because they ride the same spec/branch
and the same `deploy-sam-members` trigger:

- **Task 2** removes the Flask-plane vendored `landing_page_styles.py` from the Members layer and
  ships the SAM-owned `sam/shared/page_styles/` generator instead.
- **Task 7.2** cuts the renderer over from importing the (now-removed) Flask module to invoking the
  SAM-owned `render_page_styles` via the injected reader.

If these deployed separately there would be a broken window:

- layer-first (task 2 only): the renderer would still import the Flask module that the layer no
  longer ships → `ImportError` at publish time;
- renderer-first (task 7.2 only): the renderer would call the SAM generator that the layer has not
  yet shipped → `ImportError` at publish time.

Because both changes are under the `sam/members/**` + `sam/shared/**` deploy filters and merge in
one PR, the `sam build` + `sam deploy` packages the new layer **and** the new renderer in the same
artifact — there is no intermediate state where the layer lacks the SAM generator while the
renderer still imports the Flask module. **Do not split this feature's layer and renderer changes
across two deploys.**

## Production-release gate — promote `test` → `main` (steering 43 runbook)

A merge to `main` IS a production deploy. Promote this feature through the steering-43
promote-to-prod runbook:

1. **TEST is green & verified** — the Full Test Suite (or a dispatch with `scope: sam` +
   `scope: frontend`) passes on `test`, and the feature is exercised in live TEST (author a
   `look_and_feel` value → publish → confirm the published form carries the styling), not units
   alone. The real-data round-trip (task 11) is the non-negotiable evidence here (steering 39).
2. **One PR `test` → `main`** for the whole promotion.
3. **Preview the prod changeset** — `sam deploy --config-env prod --no-execute-changeset` from
   `sam/members`; confirm **no unexpected `Replacement: True`** on any stateful resource. This
   feature adds no new resource and only updates the layer + function code, so the changeset should
   show in-place `Modify` only — an unexpected replacement is a STOP.
   - **3a. Preview IaC changesets too** — steering 43 requires previewing `infrastructure/*.tf`
     with `terraform plan -out=tf.plan` (confirming no `# forces replacement` on a stateful/shared
     resource, applied in the same release window as the merge). **N/A for this feature** — it
     changes no `infrastructure/*.tf` (git-clean; see the IaC subsection above), so there is no
     Terraform plan to preview or apply. Recorded here so a reader following the runbook sees the
     step was considered, not forgotten.
4. **Security gates green on the PR** — **CodeQL Advanced** and **GitGuardian** must both pass; fix
   root causes, never suppress (steering 43). Note the `error_response`/no-`str(e)` convention
   already applied to the authoring routes avoids the `py/stack-trace-exposure` CodeQL finding.
5. **Merge with a MERGE COMMIT** (not squash) to preserve the spec's phase history on `main`.
6. **Watch the deploy** — the merge fires `deploy-sam-members` (and `deploy-frontend` once the
   task-12 authoring UI lands under `frontend/**`). Confirm `success` and that the Members stack
   settles `UPDATE_COMPLETE`.

### Non-negotiables (steering 43)

- Never push straight to `main` — production goes through a reviewed PR.
- No AWS secrets in CI — OIDC + `NonprofitDeployRole` only.
- Branch decides the env — never hard-code `prod`/`test`.
- A merge to `main` IS a production deploy — treat every `test` → `main` merge as a release.
