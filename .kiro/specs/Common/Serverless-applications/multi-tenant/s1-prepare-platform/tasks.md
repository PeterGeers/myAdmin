# S1 — Prepare myAdmin to Host SAM-Backed Modules — Tasks

- Status: Draft
- Roadmap step: S1 (`.kiro/specs/multi-tenant/Analysis/overall_roadmap.md`)
- Requirements: `requirements.md` · Design: `design.md`
- Decision of record: ADR 0003

> S1 is platform capability + governance, not a module implementation. No SAM app is
> built or deployed here. Chunks target < 1 day. Governance/spec updates are part of
> the definition of done (keep-governance-current).

## Phase 1 — Module descriptor: backing kind (R1, R4)

- [x] **T1.1** Add an optional `backing` block to the `MODULE_REGISTRY` schema in
      `backend/src/services/module_registry.py` (`kind`: `"flask"` default | `"sam"`;
      for `sam`: `api_base_env`, optional `data_namespace`). Do **not** add a
      `backing` key to FIN/ZZP/STR/TENADMIN — they must stay implicitly `flask`.
      _(R1.1, R4.1)_
- [x] **T1.2** Add a read-only accessor `module_backing(module_name) -> "flask"|"sam"`
      (defaults to `flask` when absent) so call sites never inspect the dict shape.
      _(R1.1)_
- [x] **T1.3** Add `resolve_module_api_base(module_name)` that, for a `sam` module,
      reads the env var named by `api_base_env` and **fails fast** if unset (no
      fallback URL). Flask modules return `None`. _(R1.2)_
- [x] **T1.4** Confirm `depends_on`, `required_roles`, `has_module()`,
      `module_required()`, `activate_module()`, and provisioning are backing-agnostic;
      add a short docstring note that entitlement is identical for both kinds.
      _(R1.3, R2.2, R4.1)_
- [x] **T1.5 (tests)** Unit tests: existing four modules load and report `flask`; a
      fixture `sam` module reports `sam` and resolves its API base from env (and
      raises when the env var is missing). No change to the intersection-auth behavior
      in `tenant_module_routes.py`. _(R4.1, R4.2)_

## Phase 2 — Document the four-seam plug-in contract (R2, R3)

- [x] **T2.1** Write the contract as a reference doc a future module author follows:
      Register → Entitle → Authorize (verified token only, no request-time MySQL) →
      Scope (`tenant_id` + IAM `LeadingKeys`). Location: alongside this spec (e.g.
      `s1-prepare-platform/module-contract.md`) and linked from steering. _(R2)_
- [x] **T2.2** In the contract, mark the enabling dependencies explicitly: Authorize
      needs S2 (signature verification on the module plane) + S4 (entitlement in the
      token); tenant-level module data needs S3 (read-only MySQL→DynamoDB projection);
      `tenant_id` on real data is S5. State that a module must **not** be built against
      the module plane until S2–S4 provide the token path. _(R2.3, R3.2)_
- [x] **T2.3** Record the two-plane data-ownership rule: MySQL is system of record;
      Lambdas authorize from the token and read their own DynamoDB / the read-only
      projection — never a request-time MySQL query; cross-plane calls pass the token
      through API Gateway. _(R3)_

## Phase 3 — Fold platform governance into myAdmin steering (R5)

> Salvage the reusable `mysaas` steering; author under myAdmin-as-base; reference
> ADR 0003. Fold in, do not fork. (This is task #4 in the working plan.)

- [x] **T3.1** Create `myAdmin/.kiro/steering/identity.md` from mysaas `identity.md` —
      keep the two-pool audience model, tiers, verification, Pool A/B relationships,
      deferred edge cases; drop the "mysaas platform" title framing. _(R5.1, R5.2)_
- [x] **T3.2** Create `myAdmin/.kiro/steering/aws-accounts.md` from mysaas
      `aws-accounts.md` — identity vs nonprofit account model, pools, guardrails,
      tenant keys. _(R5.1, R5.2)_
- [x] **T3.3** Fold the platform product framing (tenant shapes, two audiences,
      tenant-neutral rule, domains hosted as modules) into myAdmin `product.md`;
      rewrite "from myAdmin / from H-DCN rebuilt" as "hosted as modules." _(R5.1)_
- [x] **T3.4** Confirm the "Platform Evolution" section already added to myAdmin
      `architecture.md` matches this design (two planes, module contract, data
      ownership); adjust if drifted. _(R5.1)_
- [x] **T3.5** Do **not** copy mysaas `structure.md` (trunk/definition-of-record) or
      `migration-workflow.md` (migrate-into-trunk). Note in the S1 record why they are
      excluded (contradict ADR 0003). _(R5.3)_
- [x] **T3.6 (skills)** Merge mysaas `pr-checklist.md`'s two-plane items into myAdmin
      `skills/pr-checklist.md` (verified-JWT/JWKS, DynamoDB `tenant_id`+`LeadingKeys`,
      API Gateway authorizer, module handlers never query MySQL at request time,
      test-environment validation), reframed as "Flask plane + SAM-backed module
      plane"; drop the `migration-workflow.md` reference. _(R5.4)_
- [x] **T3.7 (skills)** Fold mysaas `specs-reference.md`'s reasoning-vs-ADR-vs-steering
      convention + roadmap-linkage into myAdmin `skills/specs-reference.md`; correct
      paths (no `admin/backend`, `portal/backend`, `mysaas`) and ADR refs (0003, not
      0001/0002). _(R5.4)_

## Phase 4 — Reconcile downstream specs (R6)

- [x] **T4.1** Edit `s2-jwt-verification/requirements.md`, `design.md`, `tasks.md`:
      "admin plane in `mysaas/admin/`" → "myAdmin Flask plane"; "portal plane rebuilt
      from h-dcn" → "SAM-backed module plane"; remove S6b CI/CD-cutover framing (ship
      through myAdmin's existing pipeline). Preserve all security substance. _(R6.1)_
- [x] **T4.2** Grep the multi-tenant spec tree for remaining `mysaas`, `mysaas/admin`,
      `S1b`, `S6b`, "rebuilt from h-dcn" references outside the intentional
      abandoned-plan records; flag any other parked spec for the same reconciliation.
      _(R6.2)_

## Phase 5 — Record + verify (R7, acceptance)

- [x] **T5.1** Confirm ADR 0003 covers S1's decisions. If Phase 1 settled a material
      sub-decision (the concrete `backing` field name/shape), append a short ADR or a
      note in ADR 0003's consequences. _(R7.1)_
- [x] **T5.2** Run the backend test suite (`pytest tests/unit/`) to confirm no
      regression to module loading, provisioning, or authorization. _(R4, acceptance)_
- [x] **T5.3** Verify the acceptance criteria in `requirements.md`: `sam` module
      expressible + four existing modules unchanged; contract documented; myAdmin
      steering carries the platform rules with no mysaas-trunk residue and ADR 0003
      refs; S2 spec reconciled. Update this spec's status to Complete. _(acceptance)_

## Dependencies / ordering

- Phase 1 → Phase 2 (contract references the `backing` shape).
- Phase 3 and Phase 4 can run in parallel with each other after Phase 2; both depend
  on the contract wording being settled.
- Phase 5 is last.

## Definition of done

- `MODULE_REGISTRY` can express a SAM-backed module; FIN/ZZP/STR/TENADMIN unchanged;
  tests green.
- The four-seam contract is documented and linked from steering, with S2–S5 marked as
  the enabling dependencies.
- myAdmin steering holds the two-pool identity, two-account, product, and
  module-hosting rules (plus the merged skills), under myAdmin-as-base, referencing
  ADR 0003 — no mysaas-trunk framing remains in active governance.
- The S2 spec reads correctly for the settled model and keeps its security content.
