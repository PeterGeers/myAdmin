# Translation Key Naming Conventions

This document defines the naming conventions for translation keys in myAdmin to ensure consistency and maintainability.

---

## General Principles

### 1. Use Hierarchical Structure

Translation keys should be organized hierarchically using dot notation:

```
namespace.category.subcategory.key
```

**Example:**

```json
{
  "common": {
    "buttons": {
      "save": "Save",
      "cancel": "Cancel"
    }
  }
}
```

### 2. Use Descriptive Names

Keys should be self-documenting and describe what they represent:

✅ **Good:**

```
user.profile.edit.title
banking.transaction.import.success
reports.filters.dateRange.label
```

❌ **Bad:**

```
text1
label2
msg
```

### 3. Use camelCase for Keys

Use camelCase for multi-word keys:

✅ **Good:**

```
dateRange
firstName
accountNumber
```

❌ **Bad:**

```
date_range
first-name
account number
```

### 4. Group Related Translations

Group related translations under common categories:

```json
{
  "buttons": {
    "save": "Save",
    "cancel": "Cancel",
    "delete": "Delete"
  },
  "messages": {
    "success": "Operation successful",
    "error": "An error occurred"
  }
}
```

---

## Namespace Organization

### Frontend Namespaces

myAdmin uses 8 namespaces to organize translations:

#### 1. common

Shared UI elements used across multiple modules

**Categories:**

- `buttons` - Action buttons (save, cancel, delete, etc.)
- `labels` - Form labels and field names
- `messages` - Generic messages (success, error, info)
- `navigation` - Menu items and navigation
- `status` - Status indicators (active, inactive, pending)
- `actions` - Action verbs (view, edit, create, update)
- `placeholders` - Input placeholders
- `validation` - Common validation messages
- `form` - Form-related text
- `table` - Table headers and pagination
- `modal` - Modal dialog text
- `filters` - Filter labels and options

**Example:**

```json
{
  "buttons": {
    "save": "Save",
    "cancel": "Cancel",
    "delete": "Delete",
    "export": "Export",
    "import": "Import"
  },
  "labels": {
    "email": "Email",
    "password": "Password",
    "name": "Name"
  }
}
```

#### 2. auth

Authentication and login

**Categories:**

- `login` - Login page
- `logout` - Logout functionality
- `unauthorized` - Unauthorized access
- `errors` - Authentication errors

**Example:**

```json
{
  "login": {
    "title": "Login",
    "email": "Email",
    "password": "Password",
    "submit": "Login",
    "forgotPassword": "Forgot password?"
  }
}
```

#### 3. reports

Financial reports and analytics

**Categories:**

- `titles` - Report titles
- `filters` - Report filters
- `export` - Export options
- `charts` - Chart labels
- `tables` - Table headers
- `periods` - Time periods
- `actions` - Report actions
- `messages` - Report messages

**Example:**

```json
{
  "titles": {
    "mutaties": "Transactions Report",
    "btw": "VAT Report",
    "aangifteIb": "Income Tax Declaration"
  },
  "filters": {
    "dateRange": "Date Range",
    "account": "Account",
    "category": "Category"
  }
}
```

#### 4. str

Short-term rental features

**Categories:**

- `processor` - File upload and processing
- `pricing` - Pricing optimizer
- `invoice` - Invoice generator
- `reports` - STR reports
- `bookings` - Booking management
- `listings` - Listing management

**Example:**

```json
{
  "processor": {
    "upload": {
      "title": "Upload Revenue File",
      "selectFile": "Select File",
      "platform": "Platform"
    }
  }
}
```

#### 5. banking

Banking and transaction features

**Categories:**

- `processor` - Banking processor
- `transactions` - Transaction list
- `import` - Import wizard
- `patterns` - Pattern management
- `accounts` - Account management

**Example:**

```json
{
  "processor": {
    "title": "Banking Processor",
    "upload": "Upload CSV",
    "import": "Import Transactions"
  }
}
```

#### 6. admin

Administration and settings

**Categories:**

- `sysAdmin` - System administrator
- `tenantAdmin` - Tenant administrator
- `tenantManagement` - Tenant management
- `userManagement` - User management
- `roleManagement` - Role management
- `healthCheck` - Health check
- `chartOfAccounts` - Chart of accounts
- `templateManagement` - Template management
- `credentials` - Credentials management
- `configuration` - Configuration settings
- `tenantDetails` - Tenant details
- `moduleManagement` - Module management
- `common` - Shared admin UI

**Example:**

```json
{
  "userManagement": {
    "title": "User Management",
    "createUser": "Create User",
    "editUser": "Edit User",
    "deleteUser": "Delete User"
  }
}
```

#### 7. errors

Error messages

**Categories:**

- `api` - API errors (HTTP status codes)
- `tenant` - Tenant errors
- `validation` - Validation errors
- `file` - File errors
- `data` - Data errors
- `banking` - Banking errors
- `str` - STR errors
- `invoice` - Invoice errors
- `report` - Report errors
- `user` - User errors
- `template` - Template errors
- `chartOfAccounts` - Chart of accounts errors
- `pages` - Error pages (404, 500, etc.)
- `boundary` - Error boundary messages
- `generic` - Generic errors

**Example:**

```json
{
  "api": {
    "badRequest": "Bad Request",
    "unauthorized": "Unauthorized",
    "forbidden": "Forbidden",
    "notFound": "Not Found",
    "serverError": "Server Error"
  }
}
```

#### 8. validation

Form validation messages

**Categories:**

- `required` - Required field messages
- `format` - Format validation
- `length` - Length validation
- `range` - Range validation
- `password` - Password validation
- `file` - File validation
- `date` - Date validation
- `business` - Business rule validation
- `banking` - Banking validation
- `str` - STR validation
- `invoice` - Invoice validation
- `user` - User validation
- `template` - Template validation
- `chartOfAccounts` - Chart of accounts validation
- `common` - Common validation

**Example:**

```json
{
  "required": {
    "field": "This field is required",
    "email": "Email is required",
    "password": "Password is required"
  },
  "format": {
    "email": "Invalid email address",
    "url": "Invalid URL",
    "phone": "Invalid phone number"
  }
}
```

---

## Naming Patterns

### Buttons and Actions

Use verb forms for buttons and actions:

```json
{
  "buttons": {
    "save": "Save",
    "cancel": "Cancel",
    "delete": "Delete",
    "create": "Create",
    "update": "Update",
    "export": "Export",
    "import": "Import",
    "search": "Search",
    "filter": "Filter",
    "reset": "Reset"
  }
}
```

### Labels and Fields

Use noun forms for labels:

```json
{
  "labels": {
    "email": "Email",
    "password": "Password",
    "firstName": "First Name",
    "lastName": "Last Name",
    "dateOfBirth": "Date of Birth"
  }
}
```

### Messages

Use descriptive phrases for messages:

```json
{
  "messages": {
    "success": "Operation successful",
    "error": "An error occurred",
    "loading": "Loading...",
    "noData": "No data available",
    "confirmDelete": "Are you sure you want to delete?"
  }
}
```

### Status Indicators

Use adjectives or past participles:

```json
{
  "status": {
    "active": "Active",
    "inactive": "Inactive",
    "pending": "Pending",
    "completed": "Completed",
    "failed": "Failed"
  }
}
```

---

## Special Cases

### Interpolation

Use descriptive variable names in curly braces:

```json
{
  "welcome": {
    "message": "Welcome, {{name}}!",
    "greeting": "Hello {{firstName}} {{lastName}}"
  }
}
```

**Usage:**

```typescript
t("welcome.message", { name: "John" }); // "Welcome, John!"
```

### Pluralization

Use singular/plural forms:

```json
{
  "items": {
    "count_one": "{{count}} item",
    "count_other": "{{count}} items"
  }
}
```

**Usage:**

```typescript
t("items.count", { count: 1 }); // "1 item"
t("items.count", { count: 5 }); // "5 items"
```

### Context-Specific Keys

Add context suffix when same word has different meanings:

```json
{
  "account": {
    "financial": "Account",
    "user": "Account",
    "bankAccount": "Bank Account",
    "chartAccount": "Chart of Accounts"
  }
}
```

---

## Best Practices

### ✅ DO

1. **Use hierarchical structure**

   ```json
   {
     "user": {
       "profile": {
         "edit": {
           "title": "Edit Profile"
         }
       }
     }
   }
   ```

2. **Group related translations**

   ```json
   {
     "buttons": {
       "save": "Save",
       "cancel": "Cancel"
     }
   }
   ```

3. **Use descriptive names**

   ```json
   {
     "dateRange": "Date Range",
     "accountNumber": "Account Number"
   }
   ```

4. **Keep keys consistent across languages**

   ```json
   // nl/common.json
   { "buttons": { "save": "Opslaan" } }

   // en/common.json
   { "buttons": { "save": "Save" } }
   ```

5. **Use camelCase for multi-word keys**
   ```json
   {
     "firstName": "First Name",
     "dateOfBirth": "Date of Birth"
   }
   ```

### ❌ DON'T

1. **Don't use generic keys**

   ```json
   {
     "text1": "Save",
     "label2": "Cancel"
   }
   ```

2. **Don't mix naming conventions**

   ```json
   {
     "first_name": "First Name",
     "lastName": "Last Name",
     "date-of-birth": "Date of Birth"
   }
   ```

3. **Don't use special characters**

   ```json
   {
     "user@profile": "User Profile",
     "save button": "Save"
   }
   ```

4. **Don't nest too deeply**

   ```json
   {
     "user": {
       "profile": {
         "edit": {
           "form": {
             "fields": {
               "name": {
                 "first": "First Name"
               }
             }
           }
         }
       }
     }
   }
   ```

5. **Don't duplicate keys across namespaces**
   - Each namespace should have unique keys
   - Use namespace prefix when referencing: `common:buttons.save`

---

## Key Naming Checklist

Before adding a new translation key, ask:

- [ ] Is the key descriptive and self-documenting?
- [ ] Does it follow the hierarchical structure?
- [ ] Is it in camelCase?
- [ ] Is it grouped with related translations?
- [ ] Does it exist in both language files?
- [ ] Is it in the correct namespace?
- [ ] Does it avoid special characters?
- [ ] Is the nesting level appropriate (2-4 levels)?

---

## Examples by Feature

### User Management

```json
{
  "userManagement": {
    "title": "User Management",
    "table": {
      "email": "Email",
      "name": "Name",
      "status": "Status",
      "roles": "Roles",
      "actions": "Actions"
    },
    "actions": {
      "create": "Create User",
      "edit": "Edit User",
      "delete": "Delete User",
      "resendInvitation": "Resend Invitation"
    },
    "modal": {
      "create": {
        "title": "Create New User",
        "email": "Email",
        "displayName": "Display Name",
        "temporaryPassword": "Temporary Password",
        "roles": "Roles"
      }
    },
    "messages": {
      "createSuccess": "User created successfully",
      "updateSuccess": "User updated successfully",
      "deleteSuccess": "User deleted successfully",
      "deleteConfirm": "Are you sure you want to delete this user?"
    }
  }
}
```

### Banking Processor

```json
{
  "processor": {
    "title": "Banking Processor",
    "tabs": {
      "upload": "Upload CSV",
      "transactions": "Transactions",
      "patterns": "Patterns"
    },
    "upload": {
      "selectFile": "Select CSV File",
      "dragDrop": "Drag and drop CSV file here",
      "processing": "Processing...",
      "success": "File uploaded successfully"
    },
    "transactions": {
      "table": {
        "date": "Date",
        "description": "Description",
        "amount": "Amount",
        "account": "Account",
        "status": "Status"
      },
      "filters": {
        "dateRange": "Date Range",
        "account": "Account",
        "status": "Status"
      }
    }
  }
}
```

---

## Maintenance

### Adding New Keys

1. Identify the appropriate namespace
2. Choose the correct category
3. Create a descriptive key name
4. Add to both language files (nl and en)
5. Run completeness check
6. Update this documentation if adding new categories

### Updating Keys

1. Update in both language files
2. Search codebase for usage
3. Update all references
4. Run tests
5. Run completeness check

### Removing Keys

1. Search codebase for usage
2. Remove all references
3. Remove from both language files
4. Run completeness check
5. Document removal reason

---

**Last Updated**: February 2026
**Version**: 1.0
