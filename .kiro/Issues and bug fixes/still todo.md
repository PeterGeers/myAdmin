# Grouping modules FIN, STR, ZZP, Admin

Same colour for all functions within a module like the module title

# Make som functions tenant dependant

- Activa beheer is CRUD and/or Read
- STR Kanaal omzet (a real FIN function but strongly related to STR)

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


# Kimmetje

CLOSED: url hoofdletter gevoelig // Als ik het test is het niet zo. Wel als ik het lowercase intik dat het weer met de hoofdletter A weergeeft

ING import bouwen // Begonnen aan de opzet// Waxht op download van Kim

CLOSED: Duidelijk maken filter tabel ipv invul tabel. (Zoek icoon in het veld gezet)

verwijder knop contacten + producten (verwijderen kan business wise alleen als er nog geen transacties mee zijn gemaakt, wel kun je de teksten en details aanpassen)

downloaden contacten / producten.

Viool grafiek ook totaal omzet


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


why do you keep testing all unit tests of which some fail and takes a lot of time. You do not want to fix them. Either focus on the scope or fix the failing tests

Update to use database framework .kiro\steering\database-patterns.md 

# ai use log table
- ad ai use in invoice processor

# test=maintence-framework
- add chakra mock test

