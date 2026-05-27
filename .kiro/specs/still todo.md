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

System Admin Role management I am sorry no precedence values in the table and the updated precedence is not retrieved after save. I will note it for further investigation now
-- is it in cognito
-- WHAT is the impact of precedence

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

# ai use log table

- Invoice processing
- Template management
- STR Price predicition

# STR Import Guesty


# MCP
You have 60 MCP tools enabled. We recommend disabling servers or tools to keep this below 50, as too many tools lead to degraded agent tool selection and high token usage consuming significant context. You can disable servers and tools from the MCP Servers view.