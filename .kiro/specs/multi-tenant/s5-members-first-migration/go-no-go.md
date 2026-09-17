# S5 — Members migration: Go / No-Go decision + lessons learned

- Status: **STUB — to be completed at the end of the Members pilot (migration-plan.md Step 6 soak).**
- Purpose: the explicit decision point (user requirement) on whether to migrate further
  h-dcn apps (Events, Webshop), plus the lessons that feed a roadmap revision.

> This is intentionally a stub. It is filled in after the pilot soak with real evidence,
> not predicted up front. Migrating further apps is **gated** on the Go decision here.

## Decision (to record at the gate)

- **Verdict:** Go / No-Go / Conditional-Go — _TBD_
- **Date / reviewer:** _TBD_

## Evidence to gather during the pilot (fill in)

- **Parity** — does migrated Members match live h-dcn for the pilot tenant?
  - Authorization incl. **regional access**: _TBD_
  - Data correctness (backfill fidelity, tenant-scoping): _TBD_
  - API contract (frontend sees no difference): _TBD_
  - Membership workflow (application → transitions → delegates): _TBD_
- **Did the myAdmin toolkit hold?** (what was reusable as-is vs. needed change)
  - Verified-auth toolkit (`sam/shared` `get_verified_claims`/`get_groups`): _TBD_
  - Entitlement (`get_entitlements`/`has_capability`, `tenant_modules`, projection): _TBD_
  - Tenant-scoping (`tenant_id` PK + `LeadingKeys`): _TBD_
  - The consolidation (18 handlers → one module): did the single-module shape work? _TBD_
- **Operational**
  - Per-step deploy + rollback worked: _TBD_
  - Cold-start / latency within budget: _TBD_
  - Cross-account Pool A trigger (if wired for the pilot) behaved; fail-safe held (no
    broken logins): _TBD_
- **Effort / ROI** — actual effort per step vs. estimate; is app-by-app worth continuing? _TBD_

## Lessons learned (fill in)

- What the platform tooling was missing / needed changing (feeds a roadmap revision): _TBD_
- What to do differently for Events / Webshop: _TBD_
- Any principle to add to steering / a new ADR: _TBD_

## Outcome routing

- **Go →** proceed to the next app migration with the refined tooling; update the roadmap.
- **Conditional-Go →** proceed after the listed changes to the tooling/approach.
- **No-Go →** record why + what would change the decision; revise the roadmap accordingly.
