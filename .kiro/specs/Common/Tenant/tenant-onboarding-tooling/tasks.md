# Tenant-Onboarding Tooling — Tasks

> Phase 1: module-centric folder/secrets convention + h-dcn members pilot migration.
> Companion to `requirements.md` and `design.md`. Onboarding is grouped by MODULE under
> `scripts/onboarding/<module>/` (no plane segment); tenant-wide secrets live under
> `scripts/tenants/<tenant>/`.
>
> **STATUS: Phase 1 COMPLETE.** All tasks done; full `sam/tests/` suite green (1193 passed).
> Changes are in the working tree (not yet committed).

## Phase 1 tasks

- [x] 1. Author the spec skeleton (requirements + design)
  - requirements.md, design.md, tasks.md; quoted mermaid diagram in design.
  - _Requirements: R1–R7_

- [x] 2. Introduce the shared `_lib` resolver with tests
  - `_lib/{__init__.py,paths.py,secrets.py}`: repo-marker path setup + secrets loader
    (`--tenant` convention, `--secrets` override, named-key errors). Unit tests green (16).
  - NOTE: initially created at `scripts/sam/onboarding/_lib/`; relocated to
    `scripts/onboarding/_lib/` in task 2b (module-centric requirement change).
  - _Requirements: R3, R4_

- [x] 2b. Relocate `_lib` to the module-centric root + add the named-credentials resolver
  - Relocated `_lib` to `scripts/onboarding/_lib`; `scripts/sam/` removed; test import →
    `scripts.onboarding._lib`.
  - Added `credential_file(secrets, purpose, tenant, *, override, base_dir)` to `_lib/secrets.py`
    (+ `tenant_dir`): resolves `credentials.<purpose>.file` relative to the tenant dir;
    `--credentials` override; `base_dir` for a `--secrets`-overridden file; named error on a
    missing purpose/entry; file-based `type` only (R2.6).
  - Resolver unit tests extended → **23 pass**.
  - _Requirements: R1.1, R2.3, R2.6, R3, R4_

- [x] 3. Establish the tenant-wide secrets convention for h-dcn
  - `scripts/tenants/h-dcn/secrets.example.json` written in the **named-credentials map** shape
    (`credentials.google_sheets.{type,file}` + `sheet_id`/`worksheet`/`folder_ids`).
  - Ignore-by-default `.gitignore` block for `scripts/tenants/*/*` with the committed
    template(s) + READMEs un-ignored — **verified via `git check-ignore`** (secrets.local.json +
    a co-located credential ignored; example + READMEs tracked). `scripts/tenants/README.md` written.
  - _Requirements: R2, R6_

- [x] 4. Relocate h-dcn members tenant config and rewire the loaders
  - `git mv`'d ONBOARDING.md, members_config.json, members_source_mapping.csv, both loaders to
    `scripts/onboarding/members/h-dcn/` (history preserved). Loaders use `_THIS_DIR`-relative
    defaults → resolve correctly post-move; stale docstring paths updated. Loader smoke
    (`load_members_config` + `load_mapping_contract`) OK; 3 dependent SAM tests updated + green.
  - _Requirements: R1.2, R4, R5.3_

- [x] 5. Relocate the generic members runners and switch them to `_lib`
  - `git mv`'d the 8 runners + cognito-users.sample.json to
    `scripts/onboarding/members/_generic/`; replaced each triple-`dirname` block with the `_lib`
    marker-walk bootstrap; rewired every by-path loader/seed import through `_lib.import_by_path`;
    kept every CLI flag. (Note: 4 of these h-dcn-payload files were later moved on to
    `members/h-dcn/` in task 8.) 5 dependent SAM tests updated. Runner tests green; dry-runs clean.
  - _Requirements: R1.1, R1.2, R4, R5_

- [x] 6. Wire the generic runners to the tenant-wide secrets file
  - `backfill-hdcn-members.py` resolves `sheet_id` / `worksheet` / the `google_sheets` credential
    from `secrets.local.json` via `_lib` on the live-sheet path; added `--secrets`; CLI flags win;
    two-level precedence (flag > secrets > loud named error) with **no legacy fallback** (the old
    external `DEFAULT_GOOGLE_CREDENTIALS_FILE` default removed). Source group made not-required.
    4 new `TestRunnerSecretsResolution` tests + edits to the affected tests; all green.
  - _Requirements: R2, R3_

- [x] 7. Update all cross-references and scanner/ignore config
  - `.gitguardian.yaml` backfill path → `_generic/` (later → `h-dcn/` in task 8); `.gitignore`
    carve-out comment → `scripts/onboarding/members/h-dcn/`; swept all `scripts/aws/*`
    docstring/usage strings across runners + ONBOARDING.md + members_config.json; `_lib/paths.py`
    docstring made past-tense. Secret scanner (`scan-secrets-local.sh`) **clean** (backfill still
    ignored at its new path). No stale `scripts/aws` / `scripts/sam/onboarding` refs remain
    outside this spec's own docs.
  - **NOT touched (out of scope):** four OTHER specs still reference old `scripts/aws/...` paths
    — `myBacklog/backlog.md`, `Members/s5k…/tasks.md` (task 4.3), `Members/s5m…/{design,tasks}.md`,
    `Members/members-modal…/{bugfix,tasks}.md`. The s5k task 4.3 + backlog are active runbooks
    pointing at moved runners; flagged for the owner to update separately.
  - _Requirements: R6_

- [x] 8. Finalize the onboarding README/contract and close the loop
  - `scripts/onboarding/README.md` (convention), `scripts/onboarding/members/_generic/README.md`
    (per-runner usage tracking), `scripts/onboarding/members/h-dcn/README.md` (tenant tools).
  - Deleted `scripts/aws/` entirely; cleared stale `__pycache__`.
  - **h-dcn-payload runners moved into the tenant folder** (post-review decision): the
    Ledenbestand importer `backfill-hdcn-members.py`, `seed-hdcn-catalog.py`,
    `seed-hdcn-members-config.py`, and `cognito-users.sample.json` now live in
    `members/h-dcn/` (co-located with the config/loaders they read). The 5 genuinely
    tenant-agnostic runners stay in `_generic/`. `project-config-to-prod.py` (generic) imports
    the tenant's seed step from `../<tenant>/`.
  - Final verification: full `sam/tests/` suite **1193 passed**; `--help` + dry-run of each
    runner clean; cross-dir seed import resolves.
  - _Requirements: R7_

## Deferred phases (out of scope for Phase 1)

- **Phase 2 — more modules:** apply the convention to `events` / `webshop` onboarding tooling.
- **Phase 3 — more tenants:** onboard additional tenants under `scripts/tenants/<tenant>/` and
  `scripts/onboarding/<module>/<tenant>/`.
- **Phase 4 — orchestration:** a higher-level entry point that runs the dry-run-first sequence
  end-to-end from `--tenant`, built on the stabilized Phase-1 contract.
- **Additional credential types:** wiring for env/token, ssh-key, etc. in the named-credentials
  map (R2.6), added when a tenant needs them.
