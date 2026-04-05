# First Login

> Logging into myAdmin and finding your way around.

## Overview

myAdmin uses AWS Cognito for authentication. You'll receive login credentials from your administrator and can get started right away.

## What You'll Need

- A modern web browser (Chrome, Firefox, Edge, or Safari)
- Your username and password (received from your administrator)

## Step by Step

### 1. Open myAdmin

Go to the URL provided by your administrator. You'll see the login screen.

### 2. Log in

Enter your username and password and click **Log in**.

!!! info
On your first login, you may be asked to change your password. Choose a strong password you can remember.

### 3. Navigation

After logging in, you'll see the main menu with the following sections:

| Menu item          | What it does                                         |
| ------------------ | ---------------------------------------------------- |
| **Banking**        | Import bank statements and manage transactions       |
| **Invoices**       | Upload and process invoices                          |
| **STR**            | Short-term rental bookings and revenue               |
| **STR Pricing**    | Pricing recommendations for rental properties        |
| **Reports**        | Dashboards, P&L, and balance sheets                  |
| **Tax**            | VAT, income tax, and tourist tax                     |
| **PDF Validation** | Check Google Drive links                             |
| **Admin**          | Settings and user management _(administrators only)_ |

### 4. Test or Production mode

In the top-right corner of the application, you'll see a toggle for **Test** or **Production** mode. New users start in test mode by default.

!!! warning
In **Production mode**, you're working with real data. Only switch when you're sure about what you're doing. See [Test vs Production](test-vs-production.md).

## Tips

- Use the **search function** in the menu to quickly navigate to a module
- Click the :material-help-circle: icon in the top-right of any page for contextual help
- Your session expires after a period of inactivity — log in again if that happens

## Troubleshooting

| Problem            | Cause                    | Solution                                               |
| ------------------ | ------------------------ | ------------------------------------------------------ |
| Can't log in       | Wrong password           | Use "Forgot password" or contact your administrator    |
| Page won't load    | Network issue            | Check your internet connection and refresh the page    |
| No modules visible | Insufficient permissions | Contact your administrator for the correct permissions |
