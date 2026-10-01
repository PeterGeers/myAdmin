# h-dcn Members — Production Onboarding Protocol

> **Status:** DRAFT for review (2026-09-22). This is the ordered, runnable protocol for
> onboarding h-dcn into the production `members` module (AWS `nonprofit-deploy`,
> `eu-west-1`). It ties together the `scripts/onboarding/members/_generic/*` building blocks and the authoritative
> field model. It is a companion to — not a replacement for — the phased runbook in
> `.kiro/specs/multi-tenant/s5d-member-scope-assignment/production-rollout-plan.md`.
>
> **Authoritative field model:** the field classification table in
> `.kiro/specs/multi-tenant/s5c-members-runnable-in-spa/design.md` (R4.10). This doc must
> not contradict it; where it adds prod decisions (UUID member_id, `M00001` format, the
> exact enum option lists) those are called out explicitly below.

---

## Decisions log (what is AGREED) — single source of truth

Every decision made while designing this onboarding, with status. If it's `AGREED` here,
it's settled; anything else is still open. (Newest context first.)

| # | Decision | Status |
| --- | --- | --- |
| D1 | Region vocabulary = the **10 real regions** from the Ledenbestand: Brabant/Zeeland, Duitsland, Friesland, Geen, Groningen/Drenthe, Limburg, Noord Holland, Oost, Utrecht, Zuid Holland. Separator/case is cosmetic (`scope_canon` folds it). | AGREED |
| D2 | `Geen` is the canonical "no region / Other" value. NO `Overig` in the region set; no alias. | AGREED |
| D3 | `Groningen/Drente` (import misspelling) → normalized to `Groningen/Drenthe` via a backfill region ALIAS (`scope_canon` can't fold the `h`). | AGREED |
| D4 | `member_id` = a minted **uuid4** (the export has no member_id column); stable, decoupled from the human number. | AGREED |
| D5 | `member_number` = source `Lidnummer` shaped to **`M00001`** (`M` + 5-digit zero-pad), a sortable Fixed string. | AGREED |
| D6 | `membership.status` → default **`active`** (no status column in the export). | AGREED |
| D7 | `joined_date` → `Datum ondertekening` date-part → else `<Aanmeldingsjaar>-01-01` → else **today (sysdate)**. | AGREED |
| D8 | `birth_date` is **NOT imported** — it is a CALCULATED field (day+month only, privacy). | AGREED |
| D9 | `email` is **optional** (required=False) platform-wide (66% of members have none). | AGREED |
| D10 | `referral_source` (`WieWatWaar`) is **free-text**, not an enum (messy historical data kept verbatim). | AGREED |
| D11 | `motor_brand` is a closed enum: Harley-Davidson / Indian / Buell / Eigenbouw. Enforced on create + on edits that TOUCH it; untouched legacy junk tolerated (partial-update-friendly). | AGREED |
| D12 | `Overig` **membership_type** IS in the model (admin-gated). Distinct from region `Geen`. | AGREED |
| D13 | `Clubblad` on a NUMBERED member → membership_type `overig`. Clubblad ORGANISATION rows (no Lidnummer) are skipped. | AGREED |
| D14 | **Non-members** (no `Lidnummer`: empty rows + clubblad orgs) are **left out** of `sam-members` — they belong in a FUTURE contact table. Reported as SKIPPED, not errors. | AGREED |
| D15 | **Duplicate member numbers** → leave ALL occurrences out (not first-wins); the data owner resolves the source conflict, then re-runs. | AGREED |
| D16 | **NO fallback to a hardcoded tenant scope model.** If the projection can't be read → SYSTEM ERROR with a clear message; if the tenant has no scope config → "not onboarded" error. Never silently substitute a placeholder. | AGREED |
| D17 | The tenant's region vocabulary lives ONLY in the tenant config (`members.scope_dimensions` in MySQL → projection). The generic SAM core (`HDCN_SCOPE_CONFIG`) must NOT carry the real 10 regions. | AGREED |
| D18 | Member CONFIG (`members.scope_dimensions` + `members.field_overlay`) is **authored, not backfilled** — 2 upsert rows via `ParameterService.set_param`. Onboarding does this with a repeatable **script** (`seed-hdcn-members-config.py`), single-sourced from an onboarding data file — not a manual UI step. | AGREED |
| D19 | Cognito pool for the SAM Members API = the **myAdmin** pool `eu-west-1_Hdp40eWmu` (PERSONAL account), NOT the h-dcn pool `eu-west-1_fcUkvwjH5` (nonprofit). Template pool-key renamed `HDCN`→`MYADMIN`. | AGREED |
| D20 | SAM deploys as its OWN stack `sam-members` (NOT `h-dcn`), on push to `main`, via GitHub OIDC (`NonprofitDeployRole`) — reusing the h-dcn repo's workflow pattern. | AGREED |

> **Data vs config vs code — the three things and how each is created:**
> - **Member DATA** (~1152 records) → the **backfill script** (transform Ledenbestand → `sam-members`). One-time onboarding migration; NOT prod runtime.
> - **Member CONFIG** (2 param rows) → **authored** via `set_param` (the `seed-hdcn-members-config.py` script). NOT a backfill.
> - **Membership-type CATALOG** (7 entries) → the **catalog seed script** (`seed-hdcn-catalog.py`) into `sam-members`.

---

## 0. Accounts, tables, guardrails (context)

- **Data plane** (DynamoDB `sam-members`, `governance_projection`, Lambda, API GW):
  AWS profile `nonprofit-deploy` (506221081911), region `eu-west-1`.
- **Identity** (Cognito pool `eu-west-1_Hdp40eWmu` — the "myAdmin" pool / Pool A, app
  client `myAdmin-client`): AWS profile `personal` (344561557829). The SAM Members API
  authenticates against THIS pool. (NOTE: `eu-west-1_fcUkvwjH5` is the SEPARATE h-dcn app
  pool in the nonprofit account — not used by myAdmin.)
- **System of record** for tenant/governance config: Flask + MySQL on Railway. The
  `members.*` parameters + `user_tenant_scope` + `user_tenant_roles` live here and are
  projected into `governance_projection` via `ProjectionSync`.
- **Guardrails (steering 23):** tables are managed OUTSIDE CloudFormation (retain);
  PAY_PER_REQUEST; `sam-` prefix at the front; never `--delete`/`--reset` a real data
  table; every script here is **dry-run-first** and **idempotent**.

---

## 1. The member record shape (what we store)

Single-table `sam-members`: PK `tenant_id`, SK `record_type#id` (see
`sam/members/repository/table_design.py`). A member record is:

```jsonc
{
  "tenant_id": "h-dcn",
  "member_id": "<UUID>",              // see §2 — stable internal id (NOT the human number)
  "personal":   { /* Fixed fields, storage bucket "personal" */ },
  "membership": { /* Fixed fields, storage bucket "membership" */ },
  "overlay":    { /* ALL tenant-added fields incl. region, motor/*, financial/*, admin/* */ }
}
```

Two orthogonal groupings — **do not conflate them**:

| Concept | What it is | Where it's defined |
| --- | --- | --- |
| **Storage group** | *where* a value is stored: `personal`, `membership`, or `overlay` | code — `FieldGroup` enum + `overlay` bucket (`fixed_fields.py` / `table_design.py`) |
| **Functional group** | *how* a field is grouped in the UI: personal, address, membership, motor, financial, administrative | tenant data — `members.field_overlay` (`functional_groups` + per-field `functional_group`) |

So `address` fields (`street`/`postal_code`/`city`/`country`) are **Fixed**, **store under
`personal`**, and only *display* under the "address" functional group. `motor` / `financial`
/ `administrative` fields are tenant **overlay** fields (except the system `created_at` /
`updated_at`, which are Fixed under `membership` but display as "administrative").

---

## 2. `member_id` — use a UUID (prod decision)

- `member_id` is the internal identity that forms the SK `member#<member_id>` and is the
  parent of all child records (memberships, delegates, payments).
- **Decision: `member_id` MUST be a UUID (uuidv4 string)** — stable, opaque, and decoupled
  from the human-facing member number. It never changes, even if the member number is
  reformatted or a member is renumbered. This avoids re-keying the whole record subtree.
- The current backfill keys `member_id` off the source `lidnummer` (see
  `hdcn_backfill.py` `FIXED_SOURCE_COLUMNS` → `"member_id"`). **For prod that must change**
  to mint a UUID per row and carry `lidnummer` as `membership.member_number` (the human
  number), not as the internal id. Capture the mapping `lidnummer → member_number`,
  `member_id = uuid4()` in the backfill (a code change — see the rollout plan Phase 2).

---

## 3. `member_number` — `M00001`, a sortable zero-padded string (prod decision)

- `member_number` is a **Fixed `string`** (never numeric) — this is deliberate so it sorts
  lexicographically and is leading-zero-safe (`M00001` < `M00002` < … < `M00010`). A numeric
  column would sort `1, 10, 2`; a zero-padded string sorts correctly.
- Per-tenant **uniqueness** is enforced by the repository via a `membernum#<member_number>`
  guard item + conditional write (Property 6) — a duplicate is rejected (409), never
  overwritten.
- The **format** is tenant Parameter config via `MemberNumberFormat` (`fixed_fields.py`):
  - **Decision for h-dcn: `prefix="M"`, `width=5`** → the effective regex is `^M\d{5}$`,
    example `M00001`. Values must be exactly `M` + 5 digits (headroom past 9999 members).
  - Author it in `members.field_overlay` as the `member_number` field's format (see §5).
- **Generation is out of scope** of the platform (manual entry / tenant hook). If the import
  carries `lidnummer` as bare integers, normalize each to the `M00001` shape during backfill
  (`f"M{int(n):05d}"`) so every stored value matches `^M\d{5}$`. Anything already in that
  shape passes through.

---

## 4. Dropdown / enum fields — the four buckets (REVIEW THIS SECTION)

> This is the section flagged for close review. Every dropdown's option list has ONE home;
> there are **four buckets**, all tenant data (no hardcoded platform vocabularies). Source:
> the s5c design "Dropdown / enum fields (R4.11)".

### Option shape (all buckets)

Every option is `{value, label{nl,en}, roles?}` (`EnumOption`, R4.11/R4.12):

```jsonc
{ "value": "erelid", "label": {"nl": "Erelid", "en": "Honorary member"}, "roles": ["Members_CRUD"] }
```

- `value` — the **stored, canonical** value (snake_case / stable). This is what lands in the
  record and what any comparison uses. Labels are display-only.
- `label` — localized `{nl,en}` display text the SPA renders.
- `roles` — **value-level role gate (R4.12)**. Omitted/empty ⇒ anyone who may edit the field
  may pick it. Non-empty ⇒ only callers holding one of those roles may select it. The
  frontend filters the dropdown as convenience; the **domain layer authoritatively rejects**
  a create/edit that sets a gated value the caller may not choose (422/403).

### Bucket 1 — Enum values on a **Fixed** field (`members.field_overlay`)

The field is universal (code) but its value list is tenant config (R4.2).

| Field (Fixed) | Storage | h-dcn options (`value` → `{nl,en}`) | Notes |
| --- | --- | --- | --- |
| `gender` | `personal` | `M`→{Man, Male}, `V`→{Vrouw, Female}, `X`→{Anders, Other}, `N`→{Wil niet zeggen, Prefer not to say} | open enum (`choices=None` in code); h-dcn supplies M/V/X/N |
| `status` | `membership` | the **closed** platform set, tenant relabels only: `application`→{Aanmelding, Application}, `pending`→{In behandeling, Pending}, `active`→{Actief, Active}, `suspended`→{Geschorst, Suspended}, `lapsed`→{Verlopen, Lapsed}, `left`→{Uitgeschreven, Left} | the state *values* are fixed (`MembershipStatus`); only labels/gating are config |

### Bucket 2 — Enum values on a **Parameter (overlay)** field (`members.field_overlay`)

Tenant-authored fields; the option list lives inside the overlay field's `choices`.

| Overlay field (functional group) | h-dcn source key | Options (`value` → `{nl,en}`) |
| --- | --- | --- |
| `magazine_pref` (membership) | `clubblad` | `ja`→{Ja, Yes}, `nee`→{Nee, No}, `digitaal`→{Digitaal, Digital} |
| `newsletter_pref` (membership) | `nieuwsbrief` | `ja`→{Ja, Yes}, `nee`→{Nee, No} |
| `privacy_consent` (membership) | `privacy` | `ja`→{Akkoord, Agreed}, `nee`→{Niet akkoord, Not agreed} |
| `referral_source` (membership) | `wiewatwaar` | **DECIDED: free-text `string`** (NOT an enum). The dataset has ~18 raw, typed-in values with near-duplicates + noise (`Anders`, `Bigtwin Bike Expo`, `Eerder lid van de H-DCN`, `Facebook`, `Fam`, `Familie`, `Harleydag`, `Instagram`, `Internet`, `Lid van de H-DCN`, `motorbeurs Utrecht`, `NA`, `Openingsrit`, `Partner`, `The Young Ones`, `Vrienden`, `Website H-DCN`, `YOUNG ONES`) — kept verbatim, no canonicalization, no validation against a list. Conditionally required for NEW applications (`show_when` member_id not_exists). |
| `payment_method` (financial) | `betaalwijze` | `incasso`→{Automatische incasso, Direct debit}, `overboeking`→{Overboeking, Bank transfer}, `contant`→{Contant, Cash} |
| `motor_brand` (motor) | `motormerk` | **enum, 4 values:** `harley_davidson`→{Harley-Davidson}, `indian`→{Indian}, `buell`→{Buell}, `eigenbouw`→{Eigenbouw, Custom-built}. **Enforced on create/edit (new members MUST pick one); legacy junk tolerated on READ.** `show_when` `membership_type` ∈ the set h-dcn decides (confirm exact set). SEE the "legacy tolerance" note below — the one edge case is editing an old member whose stored brand is junk. |

> **Note:** bucket-2 option lists (except `motor_brand`, which is a confirmed closed set) are
> examples of the SHAPE — the authoritative values are whatever h-dcn authors. Confirm each
> list during review.

> **Closed enums on OVERLAY fields (e.g. `motor_brand`) — VERIFIED current behaviour (2026-09-22).**
> Read the update path before assuming: `update_member` deep-merges the patch over the existing
> record and validates the WHOLE merged record — so a stored junk `motor_brand` IS present when
> you save an address-only change. BUT what the validators actually check:
> - `validate_fixed_fields` — FIXED fields only; never looks at overlay fields like `motor_brand`.
> - `_reject_disallowed_enum_values` — only rejects values whose option is **role-gated**; a value
>   simply "not in the choices list" is explicitly left alone ("unknown value … is left to the
>   type/reference checks").
> - There is **NO overlay-enum choice-membership check** anywhere (create OR update).
>
> Consequences:
> - **Q: "Save a new address → does it force fixing the junk motor_brand?"** → **No.** An
>   address-only save does NOT re-enforce `motor_brand`; the junk value survives untouched. ✅
>   (This is the legacy tolerance we want — for free, today.)
> - **BUT: "enforce the dropdown for NEW members" is NOT implemented either.** A create/edit can
>   set `motor_brand` to any string today; the 4-value list is not enforced for overlay enums.
>   ❌ So the "enforce for new" half needs a **code change**.
>
> DECISION / code change to add (recommended): add overlay-enum choice validation to
> `_validate_member_record`, made **partial-update-friendly** — validate `motor_brand` (and other
> overlay enums) against its `choices` ONLY when the field is PRESENT in the patch (mirror the
> `_membership_type_of` "only-when-changed" pattern already used for the catalog reference). That
> gives BOTH halves at once: enforced on create + on any edit that touches the field; an untouched
> legacy junk value on an address-only save passes. (Alternative: a one-time import cleanup mapping
> junk brands → `eigenbouw`, but that rewrites history and still doesn't enforce new writes.)

### Bucket 3 — Managed **catalog** (`membershiptype#` rows in `sam-members`)

`membership_type` (source `lidmaatschap`) references the Lidmaatschap Beheer catalog — module
DATA, not a parameter. Seeded by `scripts/onboarding/members/h-dcn/seed-hdcn-catalog.py`. **Active-only** entries
render in the dropdown; validated server-side (R5.8). Codes (canonical `value`s):

| `type_code` | `{nl,en}` label | roles gate (R4.12) |
| --- | --- | --- |
| `gewoon_lid` | {Gewoon lid, Regular member} | — |
| `gezins_lid` | {Gezinslid, Family member} | — |
| `donateur` | {Donateur, Donor} | — |
| `gezins_donateur` | {Gezinsdonateur, Family donor} | — |
| `erelid` | {Erelid, Honorary member} | `Members_CRUD` / `System_User_Management` |
| `sponsor` | {Sponsor, Sponsor} | — |
| `overig` | {Overig, Other} | `Members_CRUD` / `System_User_Management` |

> **`Overig` is back in the model** (per review). It is the "other" membership type,
> gated to admins (matching h-dcn `enumPermissions`). If added, it must be seeded in the
> catalog AND added to the backfill's `MembershipTypeMapper.DEFAULT_ALIASES`
> (`"overig" → "overig"`) so an imported `Overig` row resolves to the code — otherwise the
> backfill would reject it. (Code change; captured in the rollout plan.)

### Bucket 4 — Scope dimension (`members.scope_dimensions`)

`region` (source `regio`) — its `values` are BOTH the dropdown AND the scope vocabulary
(drives C-SCOPE filtering). Projected to `config#scope`. See §6.

### 4.1 — Where dropdown validation actually happens (the layering)

Two boundaries: the **UI is convenience**, the **SAM Lambda domain is the authority**. Overlay
validation is kept deliberately minimal in the generic core; genuinely bespoke rules go in a
tenant hook. Summary of what enforces what TODAY:

| Layer | What it does | Enforced today? |
| --- | --- | --- |
| **UI (SPA)** | renders the dropdown from the field's `choices`/`options`; hides role-gated options the caller may not pick | Yes — **convenience only**, never the security boundary |
| **SAM domain — generic (fixed fields)** | `gender`/`status` enum membership, `member_number` format, dates, required-ness (`validate_fixed_fields`) | Yes |
| **SAM domain — generic (all enums): value-level role gating** | rejects a role-restricted option the caller may not set (`_reject_disallowed_enum_values`) | Yes |
| **SAM domain — generic (overlay enums): choice-membership** | "an overlay value must be one of its `choices`" (e.g. `motor_brand` ∈ the 4 brands) | **NO — not wired** (the gap; §8) |
| **SAM domain — tenant hook** (`validate_member`, `sam/members/tenants/hdcn/`) | h-dcn-specific / cross-field rules the generic model can't express | Yes (mechanism exists; use sparingly) |

Design intent, stated plainly:
- **Options = data, not code.** Every dropdown's option list (incl. which options are `roles`-
  gated vs open) lives in tenant config (`members.field_overlay` / catalog / `scope_dimensions`),
  never as a code constant. Adding/removing options is a config edit + re-project, no deploy.
- **The UI restricts; the domain decides.** Selecting from a predefined list (some restricted,
  some open) is a UI convenience. The authoritative gate is the SAM Lambda domain.
- **Overlay validation stays LIGHT and generic.** The right fix for "enforce the dropdown" is a
  **generic, partial-update-friendly choice-membership check** (validate an overlay enum against
  its `choices` ONLY when the field is present in the write) — so EVERY tenant's overlay dropdowns
  are enforced for free, and untouched legacy values on an unrelated edit are left alone.
- **Tenant hooks are for the truly bespoke.** Reserve `validate_member`
  (`sam/members/tenants/hdcn/`) for rules the generic model can't express (cross-field logic,
  conditional requiredness beyond `show_when`, etc.) — NOT for plain "value ∈ list", which the
  generic check should own. Keep per-tenant code minimal.

---

## 5. The `members.field_overlay` payload (h-dcn overlay fields + functional groups)

This is the piece the rollout plan's step 3.0b left as a placeholder. Author it via the
Tenant-Admin members-config UI (preferred, audited) or
`ParameterService.set_param("tenant","h-dcn","members","field_overlay", <payload>)`.

```jsonc
{
  "functional_groups": [
    { "key": "personal",       "label": {"nl": "Persoonlijk",      "en": "Personal"},       "order": 10 },
    { "key": "address",        "label": {"nl": "Adres",            "en": "Address"},        "order": 20 },
    { "key": "membership",     "label": {"nl": "Lidmaatschap",     "en": "Membership"},     "order": 30 },
    { "key": "motor",          "label": {"nl": "Motor",            "en": "Motorcycle"},     "order": 40 },
    { "key": "financial",      "label": {"nl": "Financieel",       "en": "Financial"},      "order": 50 },
    { "key": "administrative", "label": {"nl": "Administratief",   "en": "Administrative"}, "order": 60 }
  ],

  // Fixed-field overrides: reassign display group + supply open-enum choices + number format.
  "fixed_overrides": {
    "personal.street":       { "functional_group": "address" },
    "personal.postal_code":  { "functional_group": "address" },
    "personal.city":         { "functional_group": "address" },
    "personal.country":      { "functional_group": "address" },

    "personal.gender": {
      "functional_group": "personal",
      "choices": [
        { "value": "M", "label": {"nl": "Man",              "en": "Male"} },
        { "value": "V", "label": {"nl": "Vrouw",            "en": "Female"} },
        { "value": "X", "label": {"nl": "Anders",           "en": "Other"} },
        { "value": "N", "label": {"nl": "Wil niet zeggen",  "en": "Prefer not to say"} }
      ]
    },

    "membership.status": {
      "functional_group": "membership",
      // relabel only — the VALUE set is the closed MembershipStatus enum (do not add values)
      "choices": [
        { "value": "application", "label": {"nl": "Aanmelding",     "en": "Application"} },
        { "value": "pending",     "label": {"nl": "In behandeling", "en": "Pending"} },
        { "value": "active",      "label": {"nl": "Actief",         "en": "Active"} },
        { "value": "suspended",   "label": {"nl": "Geschorst",      "en": "Suspended"} },
        { "value": "lapsed",      "label": {"nl": "Verlopen",       "en": "Lapsed"} },
        { "value": "left",        "label": {"nl": "Uitgeschreven",  "en": "Left"} }
      ]
    },

    // member_number format → M00001 (prefix M + 5 digits), sortable string (§3)
    "membership.member_number": {
      "functional_group": "membership",
      "format": { "prefix": "M", "width": 5 }
    }
  },

  // Tenant-added OVERLAY fields (stored under overlay.*). Each carries its functional_group,
  // type, required-ness, {nl,en} label, order, optional choices (dropdowns), and show_when.
  "fields": {
    "region": {
      "functional_group": "membership", "type": "enum", "required": false,
      "label": {"nl": "Regio", "en": "Region"}, "order": 10
      // NOTE: region option VALUES live in members.scope_dimensions (bucket 4), not here.
    },

    "magazine_pref": {
      "functional_group": "membership", "type": "enum", "required": false,
      "label": {"nl": "Clubblad", "en": "Magazine"}, "order": 20,
      "choices": [
        { "value": "ja",       "label": {"nl": "Ja",       "en": "Yes"} },
        { "value": "nee",      "label": {"nl": "Nee",      "en": "No"} },
        { "value": "digitaal", "label": {"nl": "Digitaal", "en": "Digital"} }
      ]
    },
    "newsletter_pref": {
      "functional_group": "membership", "type": "enum", "required": false,
      "label": {"nl": "Nieuwsbrief", "en": "Newsletter"}, "order": 30,
      "choices": [
        { "value": "ja",  "label": {"nl": "Ja",  "en": "Yes"} },
        { "value": "nee", "label": {"nl": "Nee", "en": "No"} }
      ]
    },
    "privacy_consent": {
      "functional_group": "membership", "type": "enum", "required": true,
      "label": {"nl": "Privacy", "en": "Privacy consent"}, "order": 40,
      "choices": [
        { "value": "ja",  "label": {"nl": "Akkoord",     "en": "Agreed"} },
        { "value": "nee", "label": {"nl": "Niet akkoord", "en": "Not agreed"} }
      ]
    },
    // referral_source — RECOMMENDED: free-text string (preserves the ~18 messy historical
    // values verbatim; see §4). No `choices` ⇒ any text accepted. This field does NOT pass
    // through scope_canon, so an ENUM here would reject historical spellings unless every
    // variant is folded to a canonical value at import (e.g. "The Young Ones"/"YOUNG ONES"
    // → young_ones; "Vrienden"/"Vriend" → via_vriend; "NA" → dropped). If you switch to an
    // enum later, add `type:"enum"` + `choices:[...]` and do that import fold first.
    "referral_source": {
      "functional_group": "membership", "type": "string", "required": false,
      "label": {"nl": "Wie/wat/waar", "en": "Referral source"}, "order": 50,
      "show_when": { "field": "member_id", "op": "not_exists" }  // required for new applications
    },

    "motor_brand": {
      "functional_group": "motor", "type": "enum", "required": false,
      "label": {"nl": "Motormerk", "en": "Motorcycle brand"}, "order": 10,
      // CONFIRM the membership_type set the motor fields apply to (placeholder below):
      "show_when": { "field": "membership.membership_type", "op": "in", "value": ["gewoon_lid", "gezins_lid", "erelid"] },
      // Closed enum for NEW/edited records. Legacy junk brands are NOT in this list — they
      // display fine (reads are never validated) but see the "legacy tolerance" note below.
      "choices": [
        { "value": "harley_davidson", "label": {"nl": "Harley-Davidson", "en": "Harley-Davidson"} },
        { "value": "indian",          "label": {"nl": "Indian",          "en": "Indian"} },
        { "value": "buell",           "label": {"nl": "Buell",           "en": "Buell"} },
        { "value": "eigenbouw",       "label": {"nl": "Eigenbouw",       "en": "Custom-built"} }
      ]
    },
    "motor_type":    { "functional_group": "motor", "type": "string", "required": false, "label": {"nl": "Type", "en": "Model"}, "order": 20 },
    "build_year":    { "functional_group": "motor", "type": "string", "required": false, "label": {"nl": "Bouwjaar", "en": "Build year"}, "order": 30 },
    "license_plate": { "functional_group": "motor", "type": "string", "required": false, "label": {"nl": "Kenteken", "en": "License plate"}, "order": 40 },

    "iban": { "functional_group": "financial", "type": "string", "required": false, "label": {"nl": "IBAN", "en": "IBAN"}, "order": 10 },
    "payment_method": {
      "functional_group": "financial", "type": "enum", "required": false,
      "label": {"nl": "Betaalwijze", "en": "Payment method"}, "order": 20,
      "choices": [
        { "value": "incasso",     "label": {"nl": "Automatische incasso", "en": "Direct debit"} },
        { "value": "overboeking", "label": {"nl": "Overboeking",          "en": "Bank transfer"} },
        { "value": "contant",     "label": {"nl": "Contant",              "en": "Cash"} }
      ]
    },

    "notes":          { "functional_group": "administrative", "type": "string", "required": false, "label": {"nl": "Notities", "en": "Notes"}, "order": 10 },
    "signature_date": { "functional_group": "administrative", "type": "date",   "required": false, "label": {"nl": "Datum ondertekening", "en": "Signature date"}, "order": 20 }
  }
}
```

> **Review notes:**
> - `region` VALUES are authored in `members.scope_dimensions` (§6), not in this overlay — the
>   overlay only declares the field so it renders in the "membership" group.
> - `status` `choices` here are **relabel-only**: do NOT add values (the platform state set is
>   closed). Adding a value the domain doesn't know will be rejected.
> - The `show_when` / `op` shapes above are illustrative — confirm against the resolved-field
>   `show_when` schema the code actually enforces before authoring.

---

## 6. Scope dimension — the 10 regions (`members.scope_dimensions`)

```jsonc
[{
  "key": "region", "field": "region",
  "label": {"nl": "Regio", "en": "Region"}, "enabled": true,
  "values": [
    "Friesland", "Oost", "Noord Holland", "Brabant/Zeeland", "Zuid Holland",
    "Utrecht", "Groningen/Drenthe", "Limburg", "Duitsland", "Geen"
  ],
  "required_for": ["Members_CRUD"]
}]
```

- Separator/case/diacritic spelling is COSMETIC — `scope_canon` folds space/`-`/`/`, so
  `Noord Holland` ≡ `Noord-Holland`. It does NOT fold `Drente`↔`Drenthe`, so the backfill
  needs a `Drente`→`Drenthe` region alias (code change) for the 105 import rows.
- `Geen` is the canonical "no region / Other" value (the import carries `Geen`, never
  `Overig`). Do not confuse this with the `membership_type` `Overig` (§4 bucket 3) — different
  fields.

---

## 6.1 Import decisions (Ledenbestand backfill) — VERIFIED against the real export 2026-09-22

The export (`.agent-output/Ledenbestand.json`, 1242 rows) is a Google-Form dump with quirks;
the backfill (`sam/members/migration/hdcn_backfill.py`) encodes these decisions. Result:
**1155 members imported, ~86 rows skipped (non-members + duplicates), 0 errors.**

**Identity**
- `member_id` = **minted uuid4** (the export has NO member_id column). Stable/opaque, decoupled
  from the human number (ONBOARDING §2).
- `member_number` = source **`Lidnummer`** shaped to **`M00001`** (`M{n:05d}`). `Lidmaatschapsnummer`
  is NOT used.

**Derived fields (no source column)**
- `status` → default **`active`** (the export has no status column; all Ledenbestand rows are
  current members). A later refactor may derive left/lapsed from `Afmelding`/`Beeindiging`.
- `joined_date` → date-part of **`Datum ondertekening`**; else **`<Aanmeldingsjaar>-01-01`**
  (Aanmeldingsjaar is a CALCULATED field, used only as a fallback input); else **today
  (sysdate)** so a numbered member is never dropped for a missing join date.
- `birth_date` → **NOT imported** (h-dcn calculated field: day+month only, "geboorte datum
  zonder jaar" — a privacy choice). `Geboorte datum` / `Geboortedag` / `-maand` / `-jaar` fold
  to overlay for a future calculated field.
- `email` → **optional** (66% of members have none; made `required=False` platform-wide).

**Membership-type mapping (`Soort lidmaatschap` → catalog code)**
- `Gewoon lid` → `gewoon_lid`; `Gezins lid` → `gezins_lid`; `Ere lid` → `erelid`;
  `Gezins Donateur zonder motor` → `gezins_donateur`; `Donateur zonder motor` → `donateur`;
  `Overig` → `overig` (admin-gated catalog type, added in A.4).
- **`Clubblad` on a NUMBERED member → `overig`** (DECISION): `Clubblad` is a magazine
  subscription, not a real membership type; a member who carries it is imported as type
  "Other". (Distinct from the Clubblad ORGANISATION rows below, which have no member number
  and are skipped entirely.)

**Rows SKIPPED (reported, non-blocking — NOT written, NOT errors)**
- **No `Lidnummer` → not a member.** The 27 fully-empty export scaffold rows AND ~56
  clubblad/organisation entries (dealers, sister clubs, sponsors — e.g. "Harley-Davidson
  Rotterdam", "KNMV", "Oude Monnink Motors BV"). These belong in a **future CONTACT table**,
  not `sam-members` (user decision: leave non-members out; build a contact table later).
- **Duplicate member numbers → leave ALL occurrences out** (DECISION): 3 `Lidnummer`s are
  reused in the source — `6560` (two different people), `6564` (two different people), `6247`
  (same person: a Clubblad entry + a full membership). Rather than an arbitrary "first-wins",
  EVERY row sharing a duplicated number is skipped so the data owner resolves the conflict in
  the source (assign new numbers / merge / drop), then re-runs. Surfaced in the fidelity report.

---

## 7. Onboarding order (the protocol)

Run each script WITHOUT `--apply` first (dry-run is the default) and review, then re-run with
`--apply`. All are idempotent.

1. **Provision the table** — `sam-members` (PK `tenant_id`, SK `sk`, PAY_PER_REQUEST):
   `MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \`
   `  backend/.venv/bin/python scripts/onboarding/members/_generic/provision-members-tables.py --apply`
2. **Author `members.scope_dimensions`** (the 10 regions, §6) in MySQL → `enqueue_sync`.
   Do this BEFORE the backfill apply so `region` canonicalizes to the right vocabulary.
3. **Author `members.field_overlay`** (§5) in MySQL → `enqueue_sync`. Fields/dropdowns/format.
4. **Seed the membership-type catalog** (§4 bucket 3), BEFORE the backfill so
   `membership_type` references resolve:
   `MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \`
   `  backend/.venv/bin/python scripts/onboarding/members/h-dcn/seed-hdcn-catalog.py --tenant h-dcn --apply`
5. **Backfill the members** — dry-run, review the fidelity report, then apply. Requires the
   prod backfill changes: `member_id = uuid4()` (§2), `lidnummer → M00001` member_number (§3),
   `Drente`→`Drenthe` + `Overig`→`overig` aliases (§4/§6):
   `MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \`
   `  backend/.venv/bin/python scripts/onboarding/members/h-dcn/backfill-hdcn-members.py --source <export> --tenant h-dcn --apply`

   **5b. Live direct-read alternative + reconciling sync (s5m, R6.5).** Instead of a `--source`
   export you can read the live Google Sheet DIRECTLY (read-only, service account — design D5/D6).
   Two MANUAL, gated prerequisites:
   - **SA key on disk.** Place the EXISTING h-dcn service-account JSON at the shared default path
     `/home/peter/projects/h-dcn/.googleCredentials.json` (re-download it from Google Cloud if
     absent — the Sheet is already shared with that SA as **Viewer**), or pass `--credentials
     <path>`. Scopes are read-only (`spreadsheets.readonly`; `+ drive.readonly` ONLY for the
     `--sheet-name` title-lookup path). The SA never writes the source.
   - **`.env` static keys STRIPPED** (steering 23): the repo `.env` exports `personal`-account keys
     + a local DynamoDB endpoint that OUTRANK `AWS_PROFILE`, so a plain run silently hits the WRONG
     account / the local emulator. Strip them, let the profile resolve, and **sanity-check identity
     FIRST** — it MUST print `506221081911` (NonprofitDeployRole):
     `env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \`
     `  aws sts get-caller-identity --profile nonprofit-deploy --region eu-west-1 --output json`

   Dry-run first (default; writes nothing), then apply. `--sheet-id` (from the URL
   `.../spreadsheets/d/<ID>/edit`) is PREFERRED; `--sheet-name '<title>'` resolves via a read-only
   Drive `files.list` (fails on 0 or >1 matches). `--reconcile` matches by `member_number`, upserts,
   and soft-flags SAM records absent from the sheet as `status='left'` (NEVER deletes); a `left`
   record back in the sheet reactivates. `--apply --reconcile` refuses on mapping errors OR duplicate
   sheet `member_number` values (R7.7).
   `env -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \`
   `  MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \`
   `  backend/.venv/bin/python scripts/onboarding/members/h-dcn/backfill-hdcn-members.py \`
   `  --sheet-id <SPREADSHEET_ID> --worksheet Ledenbestand --tenant h-dcn --apply --reconcile`

   - **Numberless rows need NO sheet edit** — an empty `Lidnummer` + an `Achternaam` becomes a
     `C_`+Achternaam CONTACT automatically (R7.2); a truly empty row is skipped; data with neither
     is reported UNMATCHABLE (not written).
   - **Re-run the config seed** — this spec changed `members_config.json` (new overlay fields
     `additional_info` / `deregistration_date` / `termination_date`, `magazine_pref` /
     `payment_method` value changes, `member_number` regex `^(M\d{5}|C_.+)$`). Those take effect in
     MySQL only once `scripts/onboarding/members/h-dcn/seed-hdcn-members-config.py` is RE-RUN (onboarding path). Live
     confirmation of the actual data read is a MANUAL gated step (needs the credentials file on
     disk) — documented here, not automated in CI.

6. **Seed / confirm user ROLES** in `user_tenant_roles` (the `Members_CRUD` capability the
   `required_for` gate needs; a Tenant_Admin to author scope). Roles are INDEPENDENT of scope.
7. **Author per-user scope grants** in `user_tenant_scope` (`{"region":["Oost"]}`, or
   `["*"]` for national) → `enqueue_sync` → `scopegrant#<email>#region`.
8. **Verify normalization (R9.5)** — read-only, expect PASS (every member region ∈ the 10):
   `MEMBERS_TABLE=sam-members GOVERNANCE_PROJECTION_TABLE=governance_projection AWS_REGION=eu-west-1 \`
   `  AWS_PROFILE=nonprofit-deploy backend/.venv/bin/python \`
   `  scripts/onboarding/members/_generic/verify-member-scope-normalization.py --tenant h-dcn --dimension region`
9. **Re-sync projection if stale** — `POST /api/tenant-admin/projection/resync` or
   `ProjectionSync.sync_administration("h-dcn")`.

**Never** run `scripts/local/onboard-hdcn-local.py` (or any overwriting seed) against prod —
it clobbers `members.scope_dimensions`.

---

## 8. Open code changes this protocol assumes (NOT yet implemented)

These are the deltas from the current code, to decide/implement during the rollout (review):

1. `HDCN_SCOPE_CONFIG` region values → the real 10 (`scope_dimensions.py`).
2. Backfill: mint `member_id = uuid4()`; map `lidnummer` → `membership.member_number` as
   `M{n:05d}` (not as `member_id`) (`hdcn_backfill.py`).
3. Backfill region alias: `Groningen/Drente` → `Groningen/Drenthe` (mirror `MembershipTypeMapper.DEFAULT_ALIASES`).
4. Catalog + mapper: add `overig` type_code (seed + `DEFAULT_ALIASES["overig"]="overig"`).
5. `member_number` format `M00001` authored in `members.field_overlay`.
6. Generic overlay-enum choice-membership validation (partial-update-friendly) in
   `_validate_member_record` (§4.1) — so `motor_brand` (and other overlay dropdowns) are
   enforced on create + on edits that touch the field, while untouched legacy junk passes.
7. **Cognito pool-key param NAMING mismatch (cosmetic but misleading — VERIFIED 2026-09-22).**
   The SAM template (`sam/members/template.yaml`) declares the verified-auth edge's pool
   registry under the key **`HDCN`**: params `HdcnCognitoIssuer` / `HdcnCognitoJwksUri` /
   `HdcnCognitoClientId` / `HdcnCognitoPoolLabel` → env `HDCN_COGNITO_*`, with
   `COGNITO_POOL_KEYS` naming that key. The shared toolkit (`sam/shared/auth_utils.py`) is
   GENERIC — the key is just a prefix label, no h-dcn logic — but the VALUES must point at the
   **myAdmin** pool `eu-west-1_Hdp40eWmu` (issuer/JWKS/client-id), NOT the h-dcn pool. As-is a
   deployer is likely to plug in the wrong (h-dcn) pool. FIX: rename the pool key to `MYADMIN`
   (params `MyAdminCognito*` → env `MYADMIN_COGNITO_*`, `COGNITO_POOL_KEYS=MYADMIN`), or at
   minimum document that the `HDCN`-keyed vars carry the myAdmin pool's issuer/JWKS/client-id.
   The API Gateway `CognitoUserPoolArn` authorizer is separate and already the myAdmin pool ARN.
