# Grouping modules FIN, STR, ZZP, Admin

Same colour for all functions within a module like the module title

# Make som functions tenant dependant

- Activa beheer is CRUD and/or Read
- STR Kanaal omzet (a real FIN function but strongly related to STR)

# Sizing of railway backend and railway mysql

0.5 tot 8 vCpu and 1 tot 8 GB

# Regular test updates

refactor /retest of unit, integrationand e2e tests to solve broken tests

## Short term to fix

\*\*\* Authentication tests (13 failures) — pre-existing Login component render issue (unrelated to this spec)
The 2 remaining failing suites are both authentication tests (authentication-flow.test.tsx and authentication.integration.test.tsx) — these are pre-existing failures unrelated to this spec (Login component import issue with React 19)
authentication-flow.test.tsx and authentication.integration.test.tsx — These are authentication integration tests that fail due to missing auth tokens/Cognito setup. These are pre-existing failures unrelated to the table filter framework migration.

# reset button for each parameter

Would it be useful to have a reset button for each parameter to reset it to default in the modal. Specially with json parameters getting messed up

Kiro
That's a solid idea, especially for the ui.tables JSON parameters. If someone accidentally breaks a column config, they'd currently need to know the original value or dig through the seed SQL to fix it. A "Reset to default" button in the edit modal would be a nice safety net.

That said, it's a separate concern from the table-filter-framework-v2 spec — it's a ParameterManagement feature enhancement. The implementation would need:

A backend endpoint (or extension of the existing one) that returns the system-scope default for a given namespace+key
A button in the edit modal that fetches and restores that default value into the form field
For ui.tables parameters specifically, the useTableConfig hook already has DEFAULTS hardcoded, but the generic approach would be to resolve the next-scope-up value from the ParameterService
Want me to create a separate spec for this, or would you rather keep it as a note and tackle it after the current migration is done?

# Time tracking

- Quick add part
  -- Missing product or NOT
  -- What about more people able to track time
  -- What about access to the time tracking app as a stand alone app (cognito/jwt impact)
  -- What is the added value
  -- How can we easy filter a period for submitting (day, week, month or year)

# Precedence cognito

System Admin Role management I am sorry no precence values in the table and the updated precedence is not retrieved after save. I will note it for further investigation now
-- is it in cognito

# Solve /t.d.ts problem

My recommendation: Option A — downgrade fast-check to 3.22.0. It's the last 3.x release, fully compatible with TS 4.9.5, and the API surface you use (fc.record, fc.array, fc.string, fc.integer, etc.) is identical. Want me to do that?

# Inmvoice processing

Check what happens if multiple tenants are loading invoices for processing at the same time.

## tenant switching slowness
The tenant switching slowness is a separate concern from the onboarding spec. Want me to note it as a finding and continue with the onboarding testing, or investigate it now?

# Kimmetje
url hoofdletter gevoelig  // Als ik het test is het niet zo. Wel als ik het lowercase intik dat het weer met de hoofdletter A weergeeft

Nu alleen PeterGeers + Goodwin Solutions zichtbaar.// Zou opgelost moeten zijn Tenant administrator openen je eigen user openen en edit selectren en dan rechten toevoegen. Ik zou ze allemaal selecteren voor nu  	
Finance_Export
Finance_Read
STR_Export
STR_Read
ZZP_CRUD
ZZP_Export
ZZP_Read

ING import bouwen // Begonnen aan de opzet

Duidelijk maken filter tabel ipv invul tabel.

verwijder knop contacten + producten,
downloaden contacten / producten.

Viool grafiek ook totaal omzet

# tenant/administration missing in invoice lines
This means that for all new tables we stick to tenant in stead of administration, I see the initial scope risks in invoices and the related invoice lines where in invoice lines there is no tgenant notr administration field.
Kiro
That's an important observation, but it's outside the scope of this pivot views feature. The naming convention (tenant vs administration) and the missing tenant isolation on invoice lines are broader architectural concerns that should be addressed in a separate spec — probably a data model normalization or tenant isolation audit.
For the pivot feature specifically: the TENANT_COLUMN_MAP pattern in the extensibility section already handles the fact that different tables may use different column names. If invoice lines don't have a tenant column at all, they'd need to be joined through their parent invoice to get tenant isolation — which is a data model concern, not a pivot concern.

# use filter frame work to replace filters
- BNB Revenue Analysis (STR Reports) + Remove sgtartdate and end date fields
- BNB Returning guests 




