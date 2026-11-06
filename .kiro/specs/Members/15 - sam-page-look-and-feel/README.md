# Members 15 — sam-page-look-and-feel

> Scope statement only. This is NOT a spec (no requirements/design/tasks) and makes no design
> decisions. It defines what this capability is for and where its boundaries lie.

## What it is

A generic, autonomous look-and-feel capability in the SAM plane that can style any HTML page SAM
produces — the application form today, the landing page once it becomes a SAM function, and future
pages. SAM owns its own tooling; it does not depend on the Flask landing plane at runtime.

## Direction / intent (stated by the user)

1. The application form's look and feel could legitimately be DIFFERENT from the landing page's —
   they are not required to be identical.
2. Per the no-sharing rule between the Flask and SAM planes, SAM must have its OWN autonomous
   tooling (not a runtime dependency on the Flask landing plane).
3. The intention is that the landing page itself becomes a SAM function.
4. Reusing the LOGIC of the landing page inside autonomous SAM settings, for a specific HTML page
   (such as the landing page), is a requirement.
5. Look-and-feel MANAGEMENT should become a GENERIC FUNCTION in the SAM plane — a reusable SAM
   capability that can style any HTML page, not a per-feature bolt-on and not out of scope.

## In scope

- A reusable SAM look-and-feel function/capability (not a per-feature bolt-on).
- SAM-owned settings for a page's look and feel, managed on the SAM plane.
- Reuse of the landing page's styling LOGIC inside this SAM capability.
- Per-page look and feel — the application form may legitimately differ from the landing page.
- Applying these settings to the published application form (resolving the current bug where
  changing look-and-feel settings has no effect on the published form).

## In scope as intent (longer arc)

- The landing page becoming a SAM function that uses this same capability.

## Out of scope / boundaries

- No runtime Flask<->SAM communication (the no-sharing rule).
- Not deciding the data model, storage location, or UI yet — that is design.

## Open questions (for design, not decided)

- Where SAM look-and-feel settings live and how they are authored.
- How much landing-page logic is reused vs. reimplemented.
- Migration / relationship with the existing Flask landing-page settings.
- Whether/how it supersedes or absorbs the existing `landing_page` branding.

## Related

- Bug: `.kiro/specs/myBacklog/published-form-ignores-landing-look-and-feel.md`
  (landing look-and-feel settings not applied to the published form).
- `.kiro/specs/Members/14 - public-pages-multi-tenant-serving/` (the published artifact + SAM
  render/publish pipeline this capability would feed).
