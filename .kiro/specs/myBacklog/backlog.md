## https://app.guesty.com/reservations?viewId=6a72237ce377681f84e3746c
Add website data loading from guesty
Strip fee can be found in stripe link reservation code

What is this : https://report.guesty.com/apps/reservations?apiKey=89b048a6196d1b5fbcbc40f8cb6b75924419bce37cd1efa83af5d4c6b230e089ddb4caaaad87ab85a5444543e00bcd0c80e18d3bb037d66aca1a1f7513fea2ff

checkin is between 2 months ago and 1 year into the future for Platform Manual



# Time tracking

- Quick add part
  -- Missing product or NOT
  -- What about more people able to track time
  -- What about access to the time tracking app as a stand alone app (cognito/jwt impact)
  -- What is the added value
  -- How can we easy filter a period for submitting (day, week, month or year)


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

