
# Grouping modules FIN, STR, ZZP, Admin
Same colour for all functions within a module like the module title
# Make som functions tenant dependant
- Activa beheer is CRUD and/or Read
- STR Kanaal omzet (a real FIN function but strongly related to STR)
# Bank verbinden (Saltedge)
Alles verwijderen button and code as they no longer provded the expected functions
# Su=izing of railway backend and railway mysql
0.5 tot 8 vCpu and 1 tot 8 GB
# Regular test updates
refactor /retest of unit, integrationand e2e tests to solve broken tests
## Shiort term to fix
*** Authentication tests (13 failures) — pre-existing Login component render issue (unrelated to this spec)
The 2 remaining failing suites are both authentication tests (authentication-flow.test.tsx and authentication.integration.test.tsx) — these are pre-existing failures unrelated to this spec (Login component import issue with React 19)
authentication-flow.test.tsx and authentication.integration.test.tsx — These are authentication integration tests that fail due to missing auth tokens/Cognito setup. These are pre-existing failures unrelated to the table filter framework migration.

## Would it be useful to have a reset button for each parameter to reset it to default in the modal. Specially with json parameters getting messed up

Kiro
That's a solid idea, especially for the ui.tables JSON parameters. If someone accidentally breaks a column config, they'd currently need to know the original value or dig through the seed SQL to fix it. A "Reset to default" button in the edit modal would be a nice safety net.

That said, it's a separate concern from the table-filter-framework-v2 spec — it's a ParameterManagement feature enhancement. The implementation would need:

A backend endpoint (or extension of the existing one) that returns the system-scope default for a given namespace+key
A button in the edit modal that fetches and restores that default value into the form field
For ui.tables parameters specifically, the useTableConfig hook already has DEFAULTS hardcoded, but the generic approach would be to resolve the next-scope-up value from the ParameterService
Want me to create a separate spec for this, or would you rather keep it as a note and tackle it after the current migration is done?

## Rwevolut sequence fix
- Use last date as sequencer and mutatie amount and saldo
- Do not load records where the processe data, saldo amount is zero CHECK Why are reords loaded that first where not

## Time tracking
- Quick add part
-- Missing product or NOT
-- What about more people able to track time
-- What about access to the time tracking app as a stand alone app (cognito/jwt impact)
-- What is the added value 
-- How can we easy filter a period for submitting (day, week, month or year)

## column name 
The verb source for the tenant/system scope in Tax rates is different from the verb scope in parameters while both have system and tenant
Good observation, but that's an existing data model difference — TaxRate uses source (tenant/system) while Parameters uses scope_origin (tenant/system). Both are pre-existing field names from the backend. Changing that would be a separate task outside this migration scope.

## Precedence cognito
System Admin Role management I am sorry no precence values in the table and the updated precedence is not retrieved after save. I will note it for further investigation now
-- is it in cognito

## Solve /t.d.ts problem
My recommendation: Option A — downgrade fast-check to 3.22.0. It's the last 3.x release, fully compatible with TS 4.9.5, and the API surface you use (fc.record, fc.array, fc.string, fc.integer, etc.) is identical. Want me to do that?