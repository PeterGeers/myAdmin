Balance sheet value




Aangifte IB banking value
Jaar 2026
Aangifte IB
Hoofdcategorie	Categorie	Bedrag
1000		€87.346,50
Kortlopende vorderingen	€-3.703,98


Liquide middelen	€97.151,18
Accounts for 1000 - Liquide middelen
Account	Description	Amount
1002	NL80RABO0107936917 RCRT	€6.972,69
1011	NL89RABO1342368843 sparen	€24.971,44
1012	NL67RABO1342368851 sparen	€56.318,67
Total: €88.262,80

Issue 1:
The sum of 
1002	NL80RABO0107936917 RCRT	€6.972,69
1011	NL89RABO1342368843 sparen	€24.971,44
1012	NL67RABO1342368851 sparen	€56.318,67  is Total: €88.262,80

Why is Liquide middelen	€97.151,18 while the 3 rows below it are €88.262,80

## v2
Aangifte IB
Hoofdcategorie	Categorie	Bedrag
1000		€87.346,50
Kortlopende vorderingen	€-3.703,98
Liquide middelen	€97.151,18
Accounts for 1000 - Liquide middelen

Account	Description	Amount
1002	NL80RABO0107936917 RCRT	€16.308,08
1011	NL89RABO1342368843 sparen	€23.390,42
1012	NL67RABO1342368851 sparen	€57.452,68
Total: €97.151,18

kortlopende schulden	€-6.100,70
2000		€225,48
3000		€-99.059,71
4000		€58.896,20
8000		€-47.408,47
RESULTAAT		€11.487,73
GRAND TOTAL		€0,00


The backend code is logically correct — both query_aangifte_ib and query_aangifte_ib_details apply identical year filters. The frontend sends the same selectedYear to both endpoints. So the discrepancy you saw is most likely caused by one of these scenarios:

Backend restart between calls: If the backend process restarted between the summary request (page load) and the detail request (you clicking to expand), the new process has a fresh cache. During that cache reload window, a race condition could briefly return stale or partial data.

Cache concurrent modification: The self.data.copy() in both methods should prevent this, but if load_additional_year is called concurrently by another request thread while your detail query is executing, the DataFrame could be modified mid-read.

A once-off glitch where the initial cache load didn't include all 2026 transactions for some reason (e.g., connection timeout, partial read from MySQL).

Since you can't reproduce it anymore, it was likely a transient issue. Would you like me to add a consistency check in the detail endpoint (verifying the detail sum matches the summary amount and logging a warning if it doesn't)? Or would you prefer I add cache-level safeguards to prevent this?