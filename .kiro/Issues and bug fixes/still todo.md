# Grouping modules FIN, STR, ZZP, Admin

Same colour for all functions within a module like the module title

# Make som functions tenant dependant

- Activa beheer is CRUD and/or Read
- STR Kanaal omzet (a real FIN function but strongly related to STR)

# Regular test updates

refactor /retest of unit, integrationand e2e tests to solve broken tests

## Short term to fix

\*\*\* Authentication tests (13 failures) — pre-existing Login component render issue (unrelated to this spec)
The 2 remaining failing suites are both authentication tests (authentication-flow.test.tsx and authentication.integration.test.tsx) — these are pre-existing failures unrelated to this spec (Login component import issue with React 19)
authentication-flow.test.tsx and authentication.integration.test.tsx — These are authentication integration tests that fail due to missing auth tokens/Cognito setup. These are pre-existing failures unrelated to the table filter framework migration.

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


# Inmvoice processing

Check what happens if multiple tenants are loading invoices for processing at the same time.

## tenant switching slowness

The tenant switching slowness is a separate concern from the onboarding spec. Want me to note it as a finding and continue with the onboarding testing, or investigate it now?

# Kimmetje

url hoofdletter gevoelig // Als ik het test is het niet zo. Wel als ik het lowercase intik dat het weer met de hoofdletter A weergeeft

ING import bouwen // Begonnen aan de opzet// Waxht op download van Kim

Duidelijk maken filter tabel ipv invul tabel. (Zoek icoon in het veld gezet)

verwijder knop contacten + producten (verwijderen kan business wise alleen als er nog geen transacties mee zijn gemaakt, wel kun je de teksten en details aanpassen)

downloaden contacten / producten.

Viool grafiek ook totaal omzet

# tenant/administration missing in invoice lines

This means that for all new tables we stick to tenant in stead of administration, I see the initial scope risks in invoices and the related invoice lines where in invoice lines there is no tgenant notr administration field.
Kiro
That's an important observation, but it's outside the scope of this pivot views feature. The naming convention (tenant vs administration) and the missing tenant isolation on invoice lines are broader architectural concerns that should be addressed in a separate spec — probably a data model normalization or tenant isolation audit.
For the pivot feature specifically: the TENANT_COLUMN_MAP pattern in the extensibility section already handles the fact that different tables may use different column names. If invoice lines don't have a tenant column at all, they'd need to be joined through their parent invoice to get tenant isolation — which is a data model concern, not a pivot concern.

# use filter frame work to replace filters

- BNB Revenue Analysis (STR Reports) + Remove startdate and end date fields
- BNB Returning guests
- email log system administrator
- Check Reference Numbers Main and sub
- STR Invoice Generator

# Facturen importeren

-- heeft een transactie geboektn met een datum in een al afgesloten periode, Zou niet mogen kunnen

# Documentaion
- Outdated documentation 
- Code changes on the fly, Local document updates but lot of referral documents not updated

# Is an orm layer fioreseen in the scope
Kiro
No. This spec deliberately avoids introducing an ORM (like SQLAlchemy). The approach is a lightweight abstraction layer — dialect helpers and a centralized DatabaseManager — while keeping raw SQL queries.
The reasoning from the root cause analysis still applies: the codebase has 1,200+ hand-written SQL queries across 96 files. Introducing an ORM on top of the abstraction layer refactoring would double the scope and risk. The abstraction layer is the pragmatic middle ground — it gives you database portability without rewriting every query into ORM model calls.
That said, once the abstraction layer is in place, adopting an ORM later becomes much more feasible since all database access is already centralized. It could be a future phase if there's a need for it.

# Import errors on bdc
failing urls 
- https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/search_reservations.html?source=nav&upcoming_reservations=1&hotel_id=5620035&lang=en&ses=ddc3b11e6559a324b0778f09821fd4fe&date_from=2026-04-01&date_to=2027-05-01&date_type=arrival

# Ideas for agentic AI in the scope of this project. 
- We now have AI invoice summary that works very well. We could remove the hard coded ones
- We have AI template support for solving templates (i have still never used)
- We have AI supported STR Price prediction (but that is still complete rubbish)

