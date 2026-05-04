# Grouping modules FIN, STR, ZZP, Admin

Same colour for all functions within a module like the module title

# Make some functions tenant optional

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


# Invoice processing

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



# Import errors on bdc
failing urls 
- https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/search_reservations.html?source=nav&upcoming_reservations=1&hotel_id=5620035&lang=en&ses=ddc3b11e6559a324b0778f09821fd4fe&date_from=2026-04-01&date_to=2027-05-01&date_type=arrival


why do you keep testing all unit tests of which some fail and takes a lot of time. You do not want to fix them. Either focus on the scope or fix the failing tests

Update to use database framework .kiro\steering\database-patterns.md 

# ai use log table

# Create a new spec under .kiro/specs/Common/Frameworks/ for "frontend-test-type-safety" to systematically fix all 41 files
Here's the situation:

Both existing specs are essentially complete (test-maintenance-framework is fully done, chakra-mock-framework has tasks 9-10 remaining but those are cleanup/docs, not related to these TS errors).

The 210 TypeScript errors are a separate concern — they're about:

vi.MockedFunction namespace not being recognized by tsc (Vitest 4.x typing issue)
Partial Response mock objects missing required properties
mockImplementation() signature changes in Vitest 4.x
A few possibly undefined strictness issues
These don't fit naturally into either existing spec. They need their own fix — either a new spec or a direct fix. Since both existing framework specs are done, I'd recommend one of:

Create a new spec under .kiro/specs/Common/Frameworks/ for "frontend-test-type-safety" to systematically fix all 41 files
Fix them directly — the patterns are mechanical (3 repeatable transforms across 41 files)
Skip for now — they don't block runtime (all tests pass), only tsc --noEmit