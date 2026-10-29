# Requirements Document

## Introduction

03b simplifies the Members field/form configuration model so the TENANT ADMINISTRATOR decides what
each field is and does, and the software merely STORES those choices verbatim and APPLIES them —
never overruling the admin with a hardcoded rule. On an application submission a human (the admin)
is the backstop: reject the application or fix the record in members-CRUD. This spec REMOVES
accumulated implicit rules (no-relax locks, forced-required/visible special-cases, the separate
"reference" apparatus, the W1/W3 write-guards) rather than adding another layer; success is
predictable behaviour the owner can hold in their head, achieved with a NET DECREASE in code.

The governing invariant: **the ONLY intrinsically-required field is `member_id` (the
system-generated UUID). Every other field — platform-base or tenant-added — is a tenant-admin
configuration field.** Decisions D1–D5 (resolved in `analysis.md`) are the source of these
requirements. No code until the design is approved; the D1c and D1d blast-radius traces are
design-phase investigations that prove the mechanics against real consumers before implementation.

Success metrics: every per-field boolean (`required`, `application_visible`, `application_required`)
is freely settable ON and OFF and PERSISTS; no field but `member_id` is software-forced; reference
handling is an ordinary enum with a per-option `allowed` flag; every enum field shows its
per-language label in display AND filters; net lines of code decrease.

## Glossary

- **Config_Field**: any member field the tenant admin configures (label, options, the three
  booleans, scope flag). Everything except `member_id`.
- **Member_Id**: the system-generated UUID; the ONLY intrinsically-required, non-configurable field.
- **Three_Booleans**: `required` (the member RECORD must have a value — members-CRUD validation),
  `application_visible` ("on form"), `application_required` ("required on form"). Mutually
  independent; each freely toggleable both ways.
- **Allowed_Flag**: a per-option boolean on a selectable field. `true` = offered in the picker;
  `false` = GRANDFATHERED (not offered for new/changed records, but existing values are kept,
  displayed, and valid on read/validation). Freely toggleable both ways.
- **Scope_Axis_Field**: a field flagged as a scope dimension (a boolean + `required_for` roles).
  Its values ARE the field's enum options; the SAM `config#scope` dimension and the Flask
  `members.scope_dimensions` mirror are DERIVED from the field on save.
- **Change_Op_Write**: the config write contract (steering 39) — one save → one re-projection, no
  whole-record replace, absent-vs-null semantics (absent = leave; explicit value = set; null =
  remove the aspect).
- **Label_Resolution**: `label[active locale] → en → nl → value`; the enum `value` is
  language-neutral (stored key), only `label` is per-language (steering 38 rule 6).

## Requirements

### Requirement 1: Only member_id is intrinsically required

**User Story:** As a tenant admin, I want to decide the requiredness of every human field, so that
the platform never blocks a member record over a field my organisation does not collect (e.g. a
records-only member with no email).

#### Acceptance Criteria

1. WHEN the platform validates a member record THEN only Member_Id SHALL be unconditionally required; every other field's requiredness SHALL come from the tenant config
2. WHEN a tenant config marks a field (including a platform-base field such as last_name, email, or phone) as not-required THEN saving a member record without that field SHALL succeed
3. WHEN a tenant config marks a field as required THEN saving a member record missing that field SHALL fail with a caller-safe, localized validation error
4. THE software SHALL NOT contain a hardcoded "this field is required" rule for any field other than Member_Id

### Requirement 2: The three booleans are independent and freely toggleable

**User Story:** As a tenant admin, I want to turn each of a field's booleans on AND off and have it stick, so that I can correct a mistake without the setting silently reverting.

#### Acceptance Criteria

1. FOR each Config_Field THE editor SHALL expose the Three_Booleans, each settable ON or OFF
2. WHEN the admin turns any of the Three_Booleans OFF and saves THEN the stored config SHALL reflect OFF, the write SHALL emit an explicit value rather than a dropped `undefined`, and a reload SHALL show OFF
3. WHEN the admin turns a boolean ON and saves THEN a reload SHALL show ON
4. THE Three_Booleans SHALL be mutually independent, so a field MAY be required on the record but not on the form, or on the form but not required, in any combination
5. NO boolean SHALL be forced-on and disabled for any field except where Requirement 1 makes Member_Id non-configurable

### Requirement 3: No special-casing of membership_type or references

**User Story:** As a tenant admin, I want membership_type to behave like any other enum, so that I can decide whether it is on the form, whether it is required, and which values are offered.

#### Acceptance Criteria

1. THE software SHALL NOT force membership_type (or any other single field) to be application-required or application-visible
2. WHEN membership_type is left OFF the application form THEN the application form SHALL still produce a valid submission, supplying the field's default value
3. A selectable field, including membership_type, SHALL be modelled as an ENUM whose options are `{value, label (per-language), allowed}`, with no distinct "reference field" kind, no separate live-catalog source, no `active_only`/soft-delete filtering apparatus, and no write-guard rejecting inline options
4. WHEN an option's Allowed_Flag is false THEN it SHALL be hidden from the picker for new or changed records, WHILE existing stored values equal to it SHALL be retained, displayed, and accepted on read and validation
5. THE Allowed_Flag SHALL be freely toggleable both ways, so a retired value can be re-enabled
6. A field MAY be saved with zero options as an in-progress state WITHOUT a save-blocking guard; any empty-options guidance SHALL be non-blocking

### Requirement 4: Uniform per-language enum labels in display and filters

**User Story:** As a user, I want every enum field to show its label in my language everywhere — in the table, the detail view, and the filters — so that I never see raw stored keys.

#### Acceptance Criteria

1. FOR every enum field THE display (table and detail) SHALL show the option's Label_Resolution, never the bare stored value when a label exists
2. FOR every enum field THE filter control SHALL present and match on the resolved per-language label, not the stored value
3. THE Members status-field filter SHALL use the resolved label like every other enum filter (resolving the recorded instance where it keyed off the stored value)
4. THE enum `value` SHALL remain language-neutral (the stored key, never translated); only `label` SHALL be per-language

### Requirement 5: The field is the single authoring surface; scope derives from it

**User Story:** As a tenant admin, I want to manage a scope field's values in one place (the field editor), so that the scope dimension used for access control always matches the field's options without my editing anything twice.

#### Acceptance Criteria

1. THE field editor SHALL be the single authoring surface for a Scope_Axis_Field's vocabulary (its enum options); there SHALL be no separate standalone scope-dimension editor
2. WHEN the admin saves a Scope_Axis_Field THEN the system SHALL derive the scope dimension from the field's options and write BOTH planes — SAM `config#scope` (authoritative) then the Flask `members.scope_dimensions` mirror (frontend-mirror model)
3. WHEN the SAM `config#scope` write fails THEN nothing SHALL be mirrored to Flask AND the admin SHALL see a caller-safe error
4. WHEN only the Flask mirror write fails THEN SAM SHALL stay authoritative AND the admin SHALL be offered a retry of just the mirror
5. WHEN a save would rename or remove a scope value that strands an existing user_tenant_scope grant THEN the system SHALL surface or block it using the existing orphaning reconciliation; grants SHALL NOT be silently stranded
6. Access-control RESOLUTION (which members a scoped caller may see) SHALL be UNCHANGED by this spec; only the authoring and derivation trigger is added

### Requirement 6: Admin choices are stored verbatim and applied; the human is the backstop

**User Story:** As a tenant admin, I want the system to store exactly what I configure and apply it to the form and members-CRUD, so that an application that fails my rules is something I review, not something the platform silently decides.

#### Acceptance Criteria

1. THE stored config SHALL equal what the admin set (round-trip fidelity; no silent coercion)
2. THE application form SHALL collect exactly the fields marked application_visible and require exactly those marked application_required
3. WHEN an application submission violates the admin-configured form rules THEN it SHALL be rejectable or fixable by the admin in members-CRUD, AND the platform SHALL NOT impose an additional hardcoded acceptance or rejection rule beyond the admin's config and Requirement 1
4. Config writes SHALL use the Change_Op_Write contract, AND invalid config SHALL be rejected at the write seam before storage or projection

### Requirement 7: The simplification is a net removal of code and rules

**User Story:** As the platform owner, I want this change to reduce complexity, so that the field/form behaviour is predictable and maintainable rather than a growing pile of special-cases.

#### Acceptance Criteria

1. THE no-relax lock, the forced-required/forced-visible special-cases, the reference apparatus (catalog injection and `active_only` filtering), the W1 inline-options write-guard, and the W3 empty-options hard block SHALL be REMOVED
2. THE change SHALL result in a net DECREASE in lines of code across the touched modules
3. ANY steering file that documented a removed rule (candidate: 38-sam-module-field-config) SHALL be updated within THIS spec (governance definition-of-done, steering 40)

## Out of Scope

- The codebase-wide error-exposure sweep (`error-exposure.md`); 03b consumes the caller-safe error principle for its own surfaces only.
- The generic json-editor framework extraction (D3: Members-specific, no alignment now).
- Access-control scope RESOLUTION changes beyond the authoring trigger (Requirement 5.6).
- OAuth, session-hardening, and tooling backlog items.

## CI/CD and Promotion (detailed in tasks.md per steering 43)

- Quality gates: CodeQL + GitGuardian per PR; the nightly Full Test Suite.
- Frontend changes deploy only from `main` (the TEST frontend is the local dev server); SAM changes deploy on push per the `deploy-sam-*` paths.
- Promotion gate (D5): `test → main` is BLOCKED until 03b lands AND the production `choices`→`options` migration (03a parity) plus any 03b data migration are run against PRODUCTION, each integrity-scan-gated, identically to TEST, before C6-class fail-loud is active there.

## Dependencies and References

- `analysis.md` (decisions D1–D5) and `principle-and-simplification-seed.md` (the promotion gate).
- Steering: 11-tech-stack, 36-config-and-parameters, 38-sam-module-field-config, 39-backend-data-access-sam-dynamodb, 30-backend-api-flask-mysql, 32-frontend-ui, 33/34-testing, 40-spec-workflow, 43-cicd-deploys, 23-aws-accounts, 41-shell-environment, 42-local-dynamodb-testing (per-task citations in tasks.md).
- Absorbs backlog items: `scope-dimension-authoring-trigger.md` (via Requirement 5) and `findings.md` #2 (via Requirement 4).
