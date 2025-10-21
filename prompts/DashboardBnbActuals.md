* Prompt for BnB actuals in myAdmin eports
** Add a dashboard BnB actuals in myAdmin Report
** The data in this dashboard should be limited to the data in the tables bnb, bnbplanned, bnbfuture for field definions see 'mysql table fields.md'

** The following filters are needed (see myFilters.md for specification)
*** Year To filter the data for a specific year
**** it must be possible to select 1 or more of the year (distinct year) by clicking on a selection field
*** Listing to select 1 or all of the possible listings
*** Channel to select 1 or more of the possible channels
*** The option to show the data per quarter [q] or month [m]
*** Filter to select the view of the table to be Listing or Channel in the column header
*** Filter to select which amounts must be shown with this list: amountGross, amountNett, amountChannelFee, amountTouristTax, amountVat (Muli selectable)

*** Display format
** The following table should be shown
*** Listing or Channel as column header (X-axis)
*** Year with quarter and month as subitems in the first Columns (Y-axis)  Must be easy to collapse or extend using a plus/minus sign before each row
**** This need the amountGross, amountNett, amountChannelFee, amountTouristTax and amountVat to be summarized by listing, and period (year, q,  m))
**** fields: Listing, year, q, m, amountGross, amountNett, amountChannelFee, amountTouristTax, amountVat
*** The option to expand thr view to q and m.


*** Table layout 
**** Y-Axis: width (120px),  1 column with year, indent 2 characters for q and another 2 for m
**** X-Axis: width (100 px for period and 60 px for each column presenting an amount) 
***** Labels must be right aligned with the amounts
**** Cells: Summarized Amount for all leveld year, q, m and total
 
**** No white line between the rows
**** Minimize space between table header and table
*** Sort order of selected rows from new to old f.e. 2025 [4,3,2,1] of [12,11,10,09,08,07,06,05,04,03,02,01], 2024, 2023