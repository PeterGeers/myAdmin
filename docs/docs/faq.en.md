# Frequently Asked Questions

> Answers to the most common questions about myAdmin.

## General

### What's the difference between Test and Production mode?

Test mode uses a separate database so you can safely practice. Production mode works with your real financial data. See [Test vs Production](getting-started/test-vs-production.md) for more details.

### How do I know which mode I'm in?

The current mode is always visible in the top-right of the navigation bar. **Test** or **Production** is clearly indicated.

### My session expired, what now?

Sessions expire after a period of inactivity. Simply log in again with your username and password. Any work that was already saved is not lost.

## Banking

### What file format does my bank statement need to be?

myAdmin accepts CSV files in Rabobank format. Download the statement from your online banking as a CSV file.

### Why are some transactions marked as duplicates?

The system checks whether a transaction was already imported based on date, amount, and description. If a transaction already exists, it's marked as a duplicate to prevent double entries. See [Handling duplicates](banking/handling-duplicates.md).

### What does "Apply Patterns" do?

This feature looks at previously assigned accounts for similar transactions and automatically applies the same assignment to new transactions. The more you use it, the smarter it gets. See [Pattern matching](banking/pattern-matching.md).

## Invoices

### How does AI invoice extraction work?

When you upload a PDF invoice, AI reads the content and automatically extracts details like supplier, amount, date, and VAT. You can always review and adjust the results before approving. See [AI extraction](invoices/ai-extraction.md).

### Can I edit an invoice after approval?

Yes, you can reopen and edit approved invoices. Go to the invoice and click **Edit**.

### Where are my invoices stored?

Invoices are stored in Google Drive. myAdmin manages the folder structure automatically. See [Google Drive](invoices/google-drive.md).

## STR (Short-Term Rental)

### Which platforms are supported?

myAdmin supports revenue files from **Airbnb** and **Booking.com**. See [Importing bookings](str/importing-bookings.md).

### What's the difference between realized and planned bookings?

**Realized bookings** are completed stays for which you've received payment. **Planned bookings** are future reservations that haven't taken place yet. See [Realized vs planned](str/realized-vs-planned.md).

## Tax

### How do I prepare my VAT declaration?

Go to **Tax** → **BTW**, select the quarter, and review the calculated amounts. The system calculates VAT based on your imported transactions and invoices. See [VAT declaration](tax/btw.md).

### Can I export the tax calculations?

Yes, all tax overviews can be exported to Excel for your own records or for your tax advisor.

## Technical

### The page loads slowly, what can I do?

- Refresh the page (F5 or Ctrl+R)
- Check your internet connection
- Try a different browser
- Contact your administrator if the problem persists

### I get an error when importing

Check that your file has the correct format (CSV for bank statements, PDF for invoices). Try downloading the file again from the source. See the troubleshooting section of the relevant module for specific solutions.
