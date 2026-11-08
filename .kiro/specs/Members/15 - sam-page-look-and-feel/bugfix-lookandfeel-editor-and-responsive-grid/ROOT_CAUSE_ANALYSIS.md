# Root-Cause Analysis — why the look-and-feel management UI does not work

**Scope (user-confirmed):** The published static HTML and the local/preview rendering IMPROVED and
are not the regression. The plain application form still works. What broke is the **look-and-feel
part of the management UI** — the admin cannot author logo / header_title / colour values, the
columns control reverts, and (adjacent) the grid does not reflow. This RCA explains the mechanism of
the failure AND why it shipped "green" in 2026 despite a full spec + 22-task bugfix.

## 1. The direct technical cause (what breaks)

One interaction decision breaks the editor. In `LookAndFeelEditor.tsx`:

```tsx
const edit = (attribute, value) => { onChange(attribute, value); onSave(attribute, value); };
const editExtra = (attribute, raw) => { ...; onExtraChange?.(...); onExtraSave?.(...); };
```

Every DOM `onChange` (i.e. EVERY KEYSTROKE in a text input) calls BOTH:
- `onChange` — lift the value for live preview (correct), and
- `onSave` — **persist to the server immediately** (wrong for a text field).

`onSave`/`onExtraSave` are wired in `ApplicationFormBuilder.tsx` to handlers that set
`settingLookAndFeel = true` for the duration of the PUT. That flag is passed back to the editor as
`saving`, and EVERY control binds `isDisabled={saving}`.

Result chain, per keystroke in the logo / header_title / colour-hex inputs:
1. type one character -> `onChange` + `onSave` fire;
2. `settingLookAndFeel = true` -> `saving = true` -> the field you are typing in becomes
   `isDisabled` mid-keystroke;
3. the PUT resolves and the success handler re-seeds the control from `res.settings` — the stored
   ONE-character value;
4. you cannot type character two.

For a `<select>` (columns/fonts/spacing/shadow) it is a single atomic commit so it mostly survives,
but it still briefly disables and can snap back on the re-seed — the "columns stuck at 2 / reverts"
symptom. So the whole class of symptoms traces to **persist-per-keystroke + disable-every-control +
re-seed-from-response**, a single wrong interaction model, not many independent bugs.

(Adjacent, same feature, different file: the responsive grid uses a fixed `repeat(N,1fr)` with a
single `@media (max-width:480px)` collapse in BOTH planes, so it does not reflow on normal
narrowing. And the logo is paste-only with no upload path, which is why a stored reference to a
never-uploaded object 404s. These are real but are layout/storage issues, catalogued as D3/D6/D15 in
`bugfix.md`; the editor-usability chain above is the "UI does not work" core.)

## 2. Why the tests passed anyway (the real root cause)

The feature had a dedicated test file — `__tests__/LookAndFeelEditor.test.tsx` — and it was green.
Reading it shows exactly why green meant nothing for this bug:

- **It drives one atomic event, never a sequence.** Every editor test does a single
  `fireEvent.change(..., { target: { value: 'dramatic' } })` and asserts a CALLBACK fired:
  `expect(onSave).toHaveBeenCalledWith('shadow_style', 'dramatic')`. A single synthetic change on a
  `<select>` is the ONE interaction that survives the broken model. No test types a SECOND character
  into a text input, so the per-keystroke disable/re-seed is never exercised.
- **It asserts calls and strings, not usability.** The assertions are "a handler was called with
  these args" and "the value contains no `:root`/`--`". None assert the control is still ENABLED
  after a change, that a two-character value is retained, or that the field is editable while a save
  is in flight. It literally cannot observe "the user can type."
- **The wiring tests mock the network as instant.** `mockSetLookAndFeel.mockResolvedValue(...)`
  resolves synchronously, so the `saving=true` window — the thing that disables the field — never
  meaningfully exists in the test. The disabled-during-flight state is invisible to the suite.
- **The one "regression" test is for a DIFFERENT crash.** There is a test guarding the
  `FormHelperText`-outside-`FormControl` white-screen — i.e. the suite's idea of "does the editor
  work" was "does it render without throwing", not "can it be operated".

So the suite proved: the controls render, the callbacks fire with values-only payloads, errors
surface as toasts. All true. None of it is "an administrator can author a value." The test asserted
that STRINGS and CALLS exist, not that BEHAVIOR works — the identical blind spot that let the
ORIGINAL spec-15 defect ship (the published CSS "contained the string" but styled nothing).

## 3. How this happens in 2026

It is not a tooling gap — the stack (vitest + Testing Library) can fully simulate typing, blur, and
in-flight state. It happened because of HOW the work was driven, and the mechanism is worth naming so
it does not recur:

1. **Tests were written to the implementation, not to the user.** Each task produced a paired test
   that mirrored the code's shape (`onChange`/`onSave` are called) instead of a user's goal (I typed
   a URL and it stuck). Tests written against the code's own seams pass by construction and re-encode
   the code's bugs as "expected".
2. **"Atomic-event" testing hid a stateful-interaction bug.** `fireEvent.change` with a final value
   is a shortcut that skips the keystroke-by-keystroke reality. The defect only exists ACROSS events
   + an async boundary; a single-event test can never see it.
3. **Mocked-instant async erased the failing window.** The bug lives in the `saving=true` interval.
   Mocking the PUT as an immediately-resolved promise deletes that interval from the test world.
4. **Green CI was treated as "done."** A full gate chain (CodeQL, GitGuardian, Full Test Suite) ran
   and passed — but every one of those checks is blind to interaction usability. "All gates green"
   was read as "feature works" when the gates never tested the feature's actual use. (The orchestrator
   — me — compounded this by reporting tasks complete on green tests + string/byte fixtures rather
   than one run of the real UI.)
5. **Agent-authored code + agent-authored tests, same blind spot, no human-in-the-loop use.** The
   same mental model that wrote persist-per-keystroke wrote the test that "verifies" it; nobody
   exercised the built UI as a person until you did. That is the loop that produces confidently-green
   broken software.

The one-sentence version: **the tests encoded the implementation's assumptions instead of the user's
behavior, async-in-flight state was mocked away, and a green gate chain was mistaken for a working
feature — so a one-line wrong interaction model shipped verified-but-unusable.**

## 4. What would have caught it (and must, going forward)

A single behavior-level test, written from the user's side, fails on the current code:

- render the real builder, `await` nothing instant — give `setLookAndFeelSetting` a DEFERRED promise;
- `userEvent.type(logoInput, 'https://cdn.example.org/logo.png')` (real per-character typing);
- assert the input is NOT disabled during typing AND its value equals the full string typed;
- `blur` -> assert exactly ONE persist call with the full value (not 30 calls, one per char);
- resize / assert the published artifact's grid reflows at an intermediate width;
- upload a logo via the real asset path and assert `logo` resolves to a reachable reference.

This is the discipline the bugfix spec (`bugfix.md`, R-A..R-E) already mandates: bug-condition tests
that drive real keystrokes + toggle the in-flight flag + compare RENDERED layout, never string/call
presence. The fix is small (two files for the editor model); the test change is the point.
