# Change approach for channel dfDirect
## Current flow
current flow for dfDirect must be replaced from import links Jabaki Direct
current processing for direct must be replaces

## New flow
### Import Links
- Import link for dfDirect is https://app.guesty.com/reservations?viewId=6a72237ce377681f84e3746c
- Add prompt for information: ## prompt:
Checkin is between 2 months ago and 1 year into the future for Platform Manual

### Import downloaded file
- See .kiro\specs\myBacklog\testdate.csv
- Gross amount is the amount in 'TOTAL PAYOUT'
- Channel fee is 4% of the gross amount
- if status is != confirmed just forget the row
