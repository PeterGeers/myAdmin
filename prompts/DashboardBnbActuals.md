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

** Piechart for table as shown: 
*** "CustomActiveShapePieChart" to the dashboard
*** Listing or Channel 
*** Amount gross
*** Add to the same row as the balance table but with phone support it should move below
*** Channel or Listing text as legend bij de vlakken

** Barchart for table: 
*** "BiaxialBarChart" to the dashboard
*** Add to the same row as the table but with phone support it should move below
*** Ledger text as legend bij de vlakken
*** graph for each selected period compare year by year


1. Revenue Trend Over Time
Line Chart (LineChart from Recharts)

X-axis: Time periods (months/quarters/years)

Y-axis: Revenue amounts

Multiple lines: Different amount types (Gross, Net, etc.)

Benefits: Shows clear trends, seasonality, growth patterns

Alternative: Area Chart for cumulative view

2. Relative Value of Listings/Channels
Pie Chart (already implemented) + Treemap Chart

Pie Chart: Good for showing proportional distribution

Treemap: Better for many listings/channels - shows size and hierarchy

Donut Chart: Alternative to pie with center space for totals

Benefits: Immediate visual comparison of relative contributions

3. Current Year vs Previous Year Gauge
Radial Bar Chart or Semi-Circle Gauge

Gauge range: 0% to 150% (or dynamic based on data)

Current position: (Current Year / Previous Year) × 100

Color coding:

Green: >100% (growth)

Yellow: 90-100% (slight decline)

Red: <90% (significant decline)

Center display: Actual percentage and absolute difference