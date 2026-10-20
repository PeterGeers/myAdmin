Testing application form after some parameter fixes
Three of the entries below (`died` projection wedge, `membership_type` catalog with no UI, `view_contexts` retired-but-present) are all residue of the Members parameter-model change: a redesign whose READ paths landed but whose authoring doors / cleanup / propagation hardening did not. Worth a single consolidating pass rather than three isolated patches.


### In which tenant is the s3 shared bucket liocated

<!-- APPENDED-FINDINGS-2026-10-17 -->

---

## Finding (2026-10-17): config is authored in Flask but only MEANINGFUL in the module — concept mix

### Proven facts (TEST: local Docker MySQL + SAM test / `test_governance_projection`)  
- MySQL `members.field_overlay` (h-dcn) `fixed_overrides["membership.status"]` carries 7 values incl. `died`/"Overleden", `updated_at = 2026-10-17 15:35:13`. (Source of truth is correct.)  
- The projected `config#fields` row lives in `test_governance_projection` (NOT `test_sam-members`), resolved from the `GOVERNANCE_PROJECTION_TABLE` env var shared by the Flask writer and the SAM reader.  
- Before a re-sync that row held only 6 status values (no `died`) stamped at `version = 2026-10-17T15:35:13` — the version/content WEDGE. A re-sync on the fixed (content-gate) backend healed it: `written=3`, and `config#fields` now carries `died` at the same version. (Proves the content-gate fix works.)  
- BUT the TenantAdmin field modal STILL does not show `died`. Root cause: the SAM reader `projection_config_reader._build_override` (for FIXED-field overrides like `membership.status`) does NOT carry `choices`/`options` — only `label/visible/required/order/functional_group/scope/application_*/format`. So the authored status vocabulary (incl. `died`) is dropped on READ when building `FixedFieldOverride`; the resolved field falls back to the platform base. (`_build_overlay_field`, for tenant-ADDED fields, DOES carry choices — hence `region` works but `membership.status` does not.)  
#### STrange statement/.  
 In the sam member overview when editing an account and when i want to change the status to died there are only the pre-existing 6 values of the enum. Died is also here not visible, So in the flake and in the sam plane the 7th field is not visible in the UI


### Why this keeps happening (the pattern)
Members config is AUTHORED in the Flask/MySQL plane but is only MEANINGFUL after the SAM/Lambda resolver interprets it (fixed base ⊕ overlay, provenance, options, show_when, scope). The data crosses a plane boundary and is re-mapped by a second set of code (the projection writer + the SAM reader). Every bug today (`died` wedge; `_build_override` dropping choices; the field modal seeding from the projection instead of the source) is a symptom of that split: two representations of one concept, maintained in two planes, that can silently disagree.

### Proposed direction (ADR-level — supersedes the premise of recent config specs)
Flask projects ONLY what it is the AUTHORITY for: identity/access — user <-> role <-> tenant (plus any genuinely cross-cutting parameters it owns, to be inventoried). The Members MODULE owns its own domain config — field definitions, enums, membership-type catalog, scope, mail — AUTHORED IN THE MODULE by a tenant administrator, gated by the user-role-tenant Flask provides. Config then lives where its resolving logic lives: no projection of config, no two mappers, no mix-and-match of whole concepts. Projection shrinks to a small, stable identity/access fact set.

- Removes the entire class of bug hit today (projection/mapper mismatch becomes impossible when config is not projected).
- Matches ownership to authority: Flask owns identity; the module owns its domain.
- OPEN QUESTION (first task of this direction): inventory exactly which items must still cross Flask -> module, and whether any parameter genuinely must be Flask-owned.

### Immediate (tactical) alternative if the above is deferred
Fix `_build_override` to carry `choices`/`options` (mirror `_build_overlay_field`), add the fields to `FixedFieldOverride`, confirm `FieldResolver._apply_override` applies them, + SAM tests. This patches `died` specifically but does NOT remove the concept mix.

#### UPDATE (2026-10-17, deeper root cause — supersedes the "reader-only" premise above)

Tracing the FULL chain (frontend modal -> stored param -> projection builder -> SAM reader -> resolver) shows the reader `_build_override` gap is the LAST drop, not the first cause. The real defect is an author-key / model-key MISMATCH:

- **Two representations of one enum vocabulary:** `options` (rich — `{value, label{nl,en}, roles?}`) and `choices` (bare value list). There is NO per-option sequence number; option order is just list order. `EnumOption` is exactly `{value, label, roles?}`. Field-level `order` positions the FIELD, not an option.
- **The Tenant Admin modal authors the rich vocabulary under the key `choices`, never `options`.** `EnumOptionsEditor` edits rich objects; `MembersFieldModal.buildField()` writes them to `field.choices` and the edit patch carries `choices` (never `options`). So the stored `members.field_overlay` `fixed_overrides["membership.status"]` holds the vocabulary under `choices` with NO `options` key.
- **Every backend coherence/carry/resolve path is keyed on `options`:**
  - Projection builder `_map_fixed_override` derives a coherent `choices` ONLY `if "options" in override:` — skipped here, so it carries the authored `choices` verbatim.
  - SAM reader `_build_override` reads NEITHER `options` NOR `choices` for fixed overrides -> the vocabulary is dropped on READ -> the resolver falls back to the platform base (6 values).
  - `FixedFieldOverride` HAS an `options` field and `FieldResolver._apply_override` already honours it (`if override.options is not None`) + derives coherent `choices`. The author payload never populates it.
- **Net:** the authored value (`died`) lands in the one slot (`choices`) the fixed-override read path ignores, while all rich-aware logic waits for `options`. Backend validation treats `choices`/`options` as interchangeable INPUTS (`not choices and not options`), so the mismatch is accepted silently at save — there is NO single enforced coherence point.

**Decision (user, 2026-10-17): spec-first — do NOT implement yet.** Capture here; decide implementation as its own spec. Three candidate directions, NOT equivalent:

1. **Reader-only (narrowest).** Carry `choices`/`options` in `_build_override` (mirror `_build_overlay_field`). Unblocks `died`; leaves the `choices`-vs-`options` author-key split unreconciled. (This is the old "tactical alternative" above — now known to be a partial patch.)
2. **Author-contract + reader carry (recommended).** Frontend modal emits the rich vocabulary as `options` (with `choices` derived); + the reader carry from (1). Aligns the author payload to the model's canonical key so the already-correct `options` chain works end-to-end. Touches frontend + SAM reader (+ paired tests on both planes).
3. **Canonicalize-on-save + reader carry (most robust).** Backend normalises `options`<->`choices` at store time (`fold_members_param`/validate) so the stored param is always canonical regardless of which key the modal sends; + the reader carry. Single enforced coherence point; heals existing stored data on next save. Biggest behavioural change.

All three sit UNDER the ADR-level direction above (config owned/authored in the module) — if that ADR is adopted, the projection/mapper split that makes this bug possible goes away and the question becomes moot. Any interim fix should be chosen as a deliberate bridge, not a silent patch. Per the change-with-tests contract this spans the frontend (`MembersFieldModal`/`EnumOptionsEditor` + their vitest), the Flask builder (`_projection_config_builders` + `test_projection_builder*`), and the SAM reader (`projection_config_reader` + `sam/tests`).


---

## Questions
### where are the attributes to connect a field to the applcation form
When looking in the members tenantadmin groups/fields I do not see the attrubutes needed to define the content of the application form.
#### Question answered (2026-10-17): where is the UI to define the application-form field attributes?

There is NONE. The application form is driven by four per-field attributes on `config#fields` — `application_visible`, `application_required`, `application_choices` (enum subset), `format` (checker) — added by the application-app spec. They are projected and READ by the public form, but a repo-wide search finds ZERO authoring surface in the frontend (no `.tsx`, no service/type reference). A tenant admin currently CANNOT define which fields appear on the application form, which are required, their choice subset, or the format checker from any UI — only by hand-editing the raw `members.field_overlay` JSON. This is the same "read/consume path shipped, authoring door did not" gap as the other findings, and it is exactly the kind of in-module authoring the ADR direction above would home in the Members module.
#### To be sure
The values in the field modal: Required, Visble, Read-only are only used for the normal member attrinbutes not for the application form So the application form attributes need to be defined somewhere


# Priompt cicd

I need a proper prompt to handle CICD in .kiro\specs\code-quality-maintenance\prompts
- We have the steering file 40 that shouyld enforce the proper commands in the spec file and espacial in the tasks.md
- We have the steering file 43 that defines the CICD flow.
But every time when we are moving to moving the codebase to pr to test and later to main. Kiro keeps asking for all kind of nasty questions. Mostly I say read steering 43 and or 41 and or 40. But even then it keeps asking same questions amd I try to answer from memory. This is very annoying

# Steering files and code quality check
Is there aa mechanism to check if the steering files are still aligned with the actual state of the system. E,g, steering .kiro\steering\20-platform-architecture.md is only related to the flask plane. The SAM plane is not listed. Also the number of steering files comes bigger and bigger. Should we not reorgnize the steering files so it supports Agents in their jobs and not overkill it. Often these files are not read and the read instructions are ignored
