* Prompt for dashboard actuals in myAdmin eports
** The data in this dashboard should be limited to the data in vw_mutaties

** The following filters are needed (see myFilters.md for specification)
*** Year To filter the data for a specific jaar
**** it must be possible to select 1 or more of the jaar (distinct jaar) by clicking on a selection field
*** Administration to filter tha data on a specific Administration 
*** Display format

** The following tables should be shown
*** Balance (This need the data to be summarized by ledger from the beginning (all years including the last year) where VW is == N
**** fields: Parent, ledger, VW, jaar, kwartaal, maand, summarized(Amount)
*** Profit/Loss: This need the contain the data to be summarized by ledger for the selected Year where VW == Y)
**** fields: Parent, ledger, VW, jaar, kwartaal, maand, summarized(Amount)
*** The option to expand to kwartaal and to month

*** Table layout 
**** Y-Axis: width (120px),  1 column with Parent, indent 2 characters for ledger
**** X-Axis: width (60 px for each column presented ) A column for each year selected. 
***** Align Can the year column headers  in the  Profit/Loss table be right aligned woth the amounts
**** Cells: Summarized Amount with the option 
**** It is the intention that 1 Parent has 1-N ledgers and the Amount per Parent is summarized as well as the Total amount for all ledgers.  
**** No white line between the rows
**** Minimize space between table header and table
*** Sort order of selected rows from old to new f.e. 2023, 2024, 2025

** Piechart for Balance table: 
*** "CustomActiveShapePieChart" to the dashboard
*** Make all values positive
*** Add to the same row as the balance table but with phone support it should move below
*** Ledger text as legenda bij de vlakken

** Barchart for BProfit/Loss table: 
*** "BiaxialBarChart" to the dashboard
*** Multiply values of ledger itnms in the parent 8000 with -1
*** Add to the same row as the Profit/Loss table but with phone support it should move below
*** Ledger text as legenda bij de vlakken
*** Leave ledger 8099 Bijzondere baten en lasten out of the Graph
*** graph for each selected yearcompare year by year
*** Add message to bar chart 8099 Bijzondere baten en lasten not included