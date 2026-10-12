# Pivot Views — UI flow redesign (proposal)

> Status: PROPOSAL for review. Frontend-only. No gate/permission logic changes, no backend
> changes. Goal: reduce on-screen button clutter by grouping actions along the user's
> workflow, following common UI patterns (primary action prominent, occasional/contextual
> actions collapsed into menus, result actions appearing only in context).

## Problem

The Pivot Views panel currently shows up to ~11 buttons at once, grouped by implementation
history rather than by task. Everything competes for attention even though most actions are
irrelevant at a given moment.

### Current layout (as built)

- **Row 1 — launcher:** Set dropdown · [Jubilee year] · [Joined-after year] · **Execute** ·
  **All sets** · **Mail status**
- **Row 2 — set management** (shown when `canManageSets`): **New set** · **Save as** ·
  **Update** · **Delivery** · **Deliver now** · **Schedule**  (6 buttons in one row)
- **Row 3 — result actions** (only after Execute): **Export CSV ▾** (Save locally / Email CSV) ·
  **Mail** · **Address labels**
- Modals (unchanged): All-sets library, Mail status, Field picker, Mail compose, Delivery
  editor, Schedule editor, Labels panel, Email-CSV dialog, Delete confirm.

### Why it's confusing
- Three button clusters with no visual story; row 2's six buttons read as a wall.
- "All sets" and "Mail status" sit in the launcher row but aren't part of running a pivot.
- Set-definition management (occasional, admin-ish) has the same visual weight as the primary
  Execute action.

## Design principles applied
- **One primary action per stage.** Execute is the hero of the launcher; everything else is
  secondary.
- **Collapse occasional/contextual actions into a menu.** The six set-management buttons are
  contextual to a *selected saved set* and rarely all needed at once → a single "Manage set ▾"
  menu.
- **Show result actions only in result context** (already true) and present them as a labelled
  action bar ("Do with these results").
- **Preserve every gate exactly.** Nothing becomes more or less available; only its placement
  and grouping change. Disabled/degradation states are preserved.

## Proposed layout

### Stage 1 — Run (launcher row, primary)
`[ Set dropdown ▾ ]  [ Jubilee year ▾ ]*  [ Joined-after ▾ ]*  [ ▶ Execute ]`
- Execute stays the single solid/primary button. Year selectors appear only for their presets
  (unchanged).
- Move **All sets** and **Mail status** OUT of this row into a quiet secondary control group
  (right-aligned icon+label buttons, or a small "⋯ More" menu): `All sets` · `Mail status`.
  They are navigation/history, not part of running a pivot.

### Stage 2 — Manage the selected set (collapsed)
Replace the 6-button row with ONE **"Manage set ▾"** menu button (shown only when
`canManageSets`), containing:
- **New set** (always enabled)
- **Save as** (needs a selected set)
- **Update** (needs a selected *saved* set)
- — divider —
- **Delivery** (saved set)
- **Deliver now** (saved set; spinner while running)
- **Schedule** (saved set; disabled w/ "needs delivery" tooltip when applicable, gated by
  `canSchedule`)
Each item keeps its exact current `isDisabled`/tooltip/gate. The menu button itself can show a
subtle "set selected" affordance. (Alternative if a menu feels hidden: a 2-row grouped panel
with headings "Create" / "This set" — but a menu best matches the "reduce clutter" goal.)

### Stage 3 — Use the result (post-Execute action bar, unchanged behavior)
Keep where it is, but frame it as a labelled bar:
`Do with these results:  [ Export CSV ▾ ]  [ Mail ]  [ Address labels ]`
- Export CSV keeps its Save-locally / Email-CSV submenu.
- Mail / Address labels keep their gates (mail-enabled; label-template-exists) and their
  degradation notices when hidden.

## What explicitly does NOT change
- All capability/tenant/config gates and server-side enforcement.
- All modals and their contents (library, mail status, field picker, compose, delivery,
  schedule, labels, csv-mail, delete).
- Data flow, Execute semantics (R1.6 no auto-run), export-on-visible-rows behavior.
- i18n keys reused where possible; any new label (e.g. "Manage set", "Do with these results")
  added to BOTH nl + en.

## Testing impact
- Existing `MemberPivotViews.test.tsx` drives several actions by testid directly (e.g.
  `member-pivot-new-set`, `member-pivot-delivery`). If those move inside a menu, the tests must
  first open the menu, then click the item. Testids are PRESERVED (same ids on the menu items)
  so only the "open the menu first" step is added — assertions of behavior stay identical.
- No gate/behavior assertion is weakened.

## Open questions for you
1. Stage 2: a **menu** ("Manage set ▾") vs a **grouped two-row panel** with headings? (Menu =
   least clutter; panel = everything visible but organized.)
Answer:  a **menu** 

2. Stage 1 secondary group: **All sets** + **Mail status** as a small "⋯ More" menu, or just
   right-aligned quiet buttons?
Answer: as a small "⋯ More" 

3. Any action you want promoted to always-visible (e.g. is "Deliver now" frequent enough to
   stay a top-level button)?

Answer: I have no idea yet what it does. I just pushed on Delvier Now button on pivot Verjaardag Utrecht and it said something like handled and queued, Just afraid now what it does

## Decisions (answered by the user)
1. **Stage 2 — a MENU** ("Manage set ▾") collapsing New set / Save as / Update / Delivery /
   Deliver now / Schedule. (Not a grouped panel.)
2. **Stage 1 secondary — a "⋯ More" MENU** holding All sets + Mail status.
3. **Deliver now stays INSIDE the menu** (not promoted to a top-level button). Rationale from
   live use: it fires an irreversible `to_fixed` send with no confirmation, and was alarming to
   trigger blind. **Recommended follow-up:** add a confirm dialog before it sends
   (e.g. "Send this set's result to <recipients> now?"), mirroring the mail-compose confirm.

## Note on "Deliver now" semantics (clarified from live inspection)
`Deliver now` runs ONLY the set's STORED `to_fixed` delivery — it emails the result to the
FIXED recipient address(es) saved on that set's Delivery block (with the stored attachment:
CSV / PDF labels / none). It does NOT resolve member emails or blast the group (that is the
separate `per_recipient` mode). A set with no stored `to_fixed` delivery shows a warning and
sends nothing. Blast radius = exactly the fixed addresses the user configured.
