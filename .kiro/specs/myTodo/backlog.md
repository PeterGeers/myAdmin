# Grouping modules FIN, STR, ZZP, Admin

Same colour for all functions within a module like the module title
Reiorganize finance functions (Doing[import, Mutaties]  and Reporting

# Time tracking

- Quick add part
  -- Missing product or NOT
  -- What about more people able to track time
  -- What about access to the time tracking app as a stand alone app (cognito/jwt impact)
  -- What is the added value
  -- How can we easy filter a period for submitting (day, week, month or year)

# Invoice processing

Check what happens if multiple tenants are loading invoices for processing at the same time.

# Kimmetje

CLOSED: url hoofdletter gevoelig // Als ik het test is het niet zo. Wel als ik het lowercase intik dat het weer met de hoofdletter A weergeeft

ING import bouwen // Begonnen aan de opzet// Waxht op download van Kim

CLOSED: Duidelijk maken filter tabel ipv invul tabel. (Zoek icoon in het veld gezet)

verwijder knop contacten + producten (verwijderen kan business wise alleen als er nog geen transacties mee zijn gemaakt, wel kun je de teksten en details aanpassen)

downloaden contacten / producten.

Viool grafiek ook totaal omzet

# Import errors on bdc

failing urls

- https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/search_reservations.html?source=nav&upcoming_reservations=1&hotel_id=5620035&lang=en&ses=ddc3b11e6559a324b0778f09821fd4fe&date_from=2026-04-01&date_to=2027-05-01&date_type=arrival

# STR Import Guesty

## Recalculation of balance sheet for validation
Out of scope: Full recalculation mode (reading all years while excluding OpeningBalance records) is a separate audit/verification feature to be wired into tenant administration as its own deliverable. See future spec: balance-verification-audit.


## ZZP Modal to manage trip presets
The database has an is_manual boolean field on each preset:

is_manual = true → user-created via the management UI
is_manual = false → auto-learned from trip history
Both show up equally on the Quick Entry screen — the user doesn't need to care how a preset was created. They just see their routes sorted by usage frequency.

Where the distinction matters:

Scenario	Manual	Auto-learned
Shown in Quick Entry	✓ (always)	✓ (top X by use_count)
User can edit	✓	✓
User can delete	✓	✓
Gets pruned if unused for 6 months	No	Yes (falls off the top X)
Created before first trip	✓ (plan ahead)	✗ (needs trips first)
So the practical value of manual presets: you can add a route you will drive (new client, new office) before you've actually driven it. Auto-learned ones only appear after you've used the route.

In the management UI, you could show a small badge ("Handmatig" / "Geleerd") to distinguish them visually, but it's purely informationa