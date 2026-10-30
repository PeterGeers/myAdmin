> **🚧 PROMOTION GATE (owner, 2026-10-29): `test` MUST NOT be promoted to `main` until this
> simplification spec is designed and landed.** The current `test` branch carries behavior that is
> both outage-risky in production AND about to be deliberately changed here:
> - **C6 fail-loud + C8 blocking guard** — production `governance_projection` very likely holds the
>   same un-migrated bare-`choices` rows that broke the TEST editor; merged to `main`, C6 would
>   raise on the staff config read / drop fields on the public form for real tenants (a members-
>   config outage). Some effects are not cleanly reversible once live.
> - The hardcoded field/form rules below are still in place; shipping now LOCKS IN the complexity
>   this spec removes, and ships the application-form toggle-off bug to real tenants.
> A `test → main` PR for the 03a work is BLOCKED until: this spec lands, a prod migration + the
> all-tenant zero-un-migrated scan pass against production, and the field/form model is simplified.

# SPEC: Admin-driven field/form model — remove hardcoded validation rules (simplification)

> **This is the originating owner note (dated).** Where it differs from the evolved spec, the
> SOURCE OF TRUTH is `requirements.md` + `design.md` (e.g. the scope gate is axis-vs-value, not the
> value-level orphan block sketched below; the booleans are not "independent" — see Req 2/4).

**Raised 2026-10-29 by the owner.** The field/form configuration has accumulated hardcoded,
implicit rules that OVERRULE the tenant administrator and interact in ways that are hard to
predict. Each was added "to be safe"; together they are accidental complexity. This spec is a
DELIBERATE SIMPLIFICATION pass — it REMOVES rules, it does not add another layer.

## Governing principle (owner decision — the design north star)
> **The tenant administrator decides what the application form collects and what is required.
> The software's job is to faithfully STORE those choices and APPLY them — not to overrule the
> admin with hardcoded rules. The form validates data entry against the admin's choices; on
> submission the admin can REJECT the application or MANUALLY FIX it in members-CRUD. The human
> is the backstop, not a wall of hardcoded guards.**

Design test for "done": a tenant admin can set any field's two form booleans ([on form] /
[required on form]) FREELY both ways, and the owner can predict EXACTLY what the form and
members-CRUD will do — with NO hidden rules. The change should REDUCE code, not grow it.

## Two plain booleans per field (the target model)
- **`application_visible`** — "[on form]": is this field shown on the application form?
- **`application_required`** — "[required]": must the applicant fill it in to submit?
Both freely toggleable ON and OFF, independently, for EVERY field (fixed-base override or tenant
variable), in every group. Plus the staff-record **`required`** (members-CRUD validation), which
is a SEPARATE, also-freely-toggleable boolean (a field can be required on the record but not the
form, or vice-versa — the admin decides).

## The hardcoded/implicit rules to REMOVE or justify (evidence from this session)
Each must be either DELETED (default) or, if genuinely required, RE-JUSTIFIED explicitly and made
visible to the admin (never a silent lock):

1. **No-relax lock on `application_required` (R8.1c / R3.1 / R4.2).** The UI FORCES the
   [required] toggle ON + disabled for a "platform-required" field and the membership-type
   reference field; the SAM write also rejects a relax. This directly contradicts the principle —
   the admin cannot turn OFF required-on-form for such a field. REMOVE the forced-on lock unless
   there is a hard data-integrity reason, and if kept, surface the reason in the UI (not a silent
   disabled toggle). Files: `ApplicationFieldAttributes.tsx` / `ApplicationFieldModal.tsx`
   (`requiredForced`), and the SAM write-side relax rejection.

2. **"membership-type is always application-required" (spec 10 D21).** Same class — a hardcoded
   special-case for one field. Re-justify or remove.

3. **`undefined`-means-leave-as-is toggle semantics (the toggle-off bug).** The field modal and
   the application-attr editors send `next ? true : undefined` on toggle-off. `undefined` is
   DROPPED by the Change-Op diff (`definitionAttrs`/`applicationAttrs` emit only when `!==
   undefined`), so a stored `true` is NEVER cleared — the admin CANNOT turn a field back off once
   on. Confirmed for staff-record `required` (fixed in commit daa11b3bc by sending explicit
   `false`) AND still live for `application_visible` / `application_required`
   (`ApplicationFieldAttributes.tsx`, `ApplicationFieldModal.tsx`). The simplification: a toggle
   OFF sends an EXPLICIT value (`false`, or `null` to REMOVE) so the admin's "off" always
   persists — uniformly, for all three booleans, all field kinds, all groups. Backend already
   supports it (`set_field`/`set_field_application` absent-vs-null semantics; resolver +
   overlay reader round-trip an explicit `false`).

4. **Platform "email/phone are special" instincts.** The platform base correctly keeps email/phone
   OPTIONAL (records-first: ~66% of h-dcn members have no email). The real failure was a tenant
   override `required: true` the admin couldn't clear (rule 3). Guard against RE-introducing any
   "this field is intrinsically required" hardcoding — requiredness is an admin choice, not a
   platform constant (beyond a minimal identity anchor like `last_name`, which should itself be
   re-justified, not assumed).

5. **Scope/W-guard overreach (this session's own regression).** The 03a review added write-edge
   guards W1/W2/W3 and a scope-as-separate-source read model that OVERRULED the established
   "field is the source of truth" design and BROKE the only authoring path (W2 blocked saving a
   scope field; removed in commit 5951b6bd1). Treat W1 (reference inline-options) and W3
   (empty-enum) with the SAME skepticism: are they protecting real integrity, or imposing a rule
   the admin should own? Keep only what a human reviewer cannot backstop. (Related, separate
   backlog item: `scope-dimension-authoring-trigger.md`.)

## Direction (a design pass — do NOT blind-patch; this is about REMOVING rules)
- **Inventory** every hardcoded/implicit rule in the field/form config + member-CRUD validation
  path (frontend editors + SAM write guards + SAM resolver + Flask validators). For each: is it
  protecting real data integrity a human cannot backstop, or is it overruling the admin? Default
  verdict = REMOVE.
- **Collapse to the plain model:** three independent, freely-toggleable booleans
  (`required` record-side, `application_visible`, `application_required`), stored exactly as set,
  no forced states, no no-relax. Any genuinely-locked case is the EXPLICIT, visible exception,
  never a silent disabled control.
- **Validation is the admin's config applied, plus the human review step:** the form requires what
  the admin marked required; a submitted application that fails is REVIEWABLE (reject or fix in
  members-CRUD), not blocked by a platform rule the admin didn't choose.
- **Success metric = less code + predictable behavior.** The toggle bug, the W-guards, the
  forced-required lock, and the undefined-vs-explicit semantics should all resolve BY this
  simplification, not by more special-case patches.

## Out of scope / dependencies
- This SUPERSEDES the piecemeal toggle fixes. The staff-record `required` fix already shipped
  (daa11b3bc) as an interim; the application-form toggle fix (rules 3) should land as PART of this
  simplification, not as another isolated patch.
- Touches members-CRUD validation and the application-form validator — regression coverage must
  prove an admin's toggle choices round-trip and are applied, and that NO hardcoded requiredness
  survives. Access-control scope is a separate concern (`scope-dimension-authoring-trigger.md`).
- Needs an explicit owner decision per retained rule (if any): keep-with-visible-reason vs remove.
