At this moment the P&L and Balance are in tab Actuals in FIN reports. 
Some confusing items in the current implementation. of the tab Actuals 
-- Balance (vw = N) - All Years Total
---- If I select 2 years (2024 and 2025) the balance of these 2 years seems Summarized. This was valid before year end closing but not any more. If a year is closed balance amounts are correct within a year but can only be summarized if Opening balances are left out or only within a year.

-- The page is a bit confusing. It would be better if there is a seperate page with the Balance info and 1 other with the P&L having similar filters

-- Strange behaviour of cache memory
---- Can you explain when data is in cache and when not. 
---- What is the button Update Data doing. (I think is is not refreshing the cache)
** The "Update Data" button calls fetchActualsData() which just re-fetches from the API (/api/reports/actuals-balance and /api/reports/actuals-profitloss). It does NOT call the cache invalidation endpoint. So if the cache is still within its 30-minute TTL, the button returns the same cached data — it doesn't actually refresh anything. That's the bug you noticed. The button needs to call the cache invalidation endpoint first, then fetch.

-- The graphs are not swapping below the tables when reducing the window. Only for mobile. It should be nice that the graphs swap when the window size reduces and the columns increase

Recommendations:
- Spilt the page actuals in 1 page Balance and 1 in P&L
- Balance (VW = N) - All Years Total make this a table with year columns and the balance value of years. Specials attention for years not closed

- Profit & Loss (VW = Y) 
--- Add expansion to current table with reference number and limit the columns to years only
--- Add a new table with year/expansion in the column and parent & account in the header


Histgram P&L distribution:
-  to reduce the blank space: Split the profit (8000) in 1 graph and the loss (4000) in 1 graph

The hook instruction says "Deprecated — see code-standards-review hook" with no exit code failure, so I'll proceed with the write.

These existing tests were already failing before my changes (they don't mock get_tenant_roles either, and the auth flow fails because there's no DB). The 2 that pass are the "requires_tenant" tests that expect 401/403. My changes didn't break anything — these were pre-existing failures.