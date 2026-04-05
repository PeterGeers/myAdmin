# Test vs Production

> When to use which mode and what's the difference?

## Overview

myAdmin has two modes: **Test mode** and **Production mode**. Each mode uses its own database, so you can safely practice without affecting real data.

## What's the difference?

|              | Test mode                         | Production mode                    |
| ------------ | --------------------------------- | ---------------------------------- |
| **Database** | Separate test database            | Production database with real data |
| **Data**     | Sample data or your own test data | Real financial data                |
| **Risk**     | None — you can't break anything   | Changes are permanent              |
| **Best for** | Learning, testing, experimenting  | Daily work                         |

## When to use Test mode?

- You're **new** and want to get to know the platform
- You want to **try a new feature** before applying it to real data
- You want to **test import files** to check if the format is correct
- You want to **test patterns** without modifying real transactions

## When to use Production mode?

- You're processing **real bank statements**
- You're uploading **real invoices**
- You're preparing **tax declarations**
- You're generating **reports** for your administration

## How to switch between modes?

1. Look at the top-right corner of the application
2. You'll see a toggle showing **Test** or **Production**
3. Click the toggle to switch modes
4. The page reloads with data from the selected database

!!! danger
Be careful when switching to **Production mode**. All changes you make (importing, deleting, editing) are permanent and affect real data.

!!! tip
Not sure? Stay in **Test mode**. You can always switch to production later.

## Tips

- The current mode is always visible in the navigation bar
- Test data and production data are completely separated
- You can import the same files in test mode as in production — it only affects the test database

## Troubleshooting

| Problem              | Cause                                            | Solution                                        |
| -------------------- | ------------------------------------------------ | ----------------------------------------------- |
| I don't see any data | You're in test mode and there's no test data yet | Import test files first or switch to production |
| My changes are gone  | You worked in test mode instead of production    | Repeat the action in production mode            |
| Can't switch         | Insufficient permissions                         | Contact your administrator                      |
