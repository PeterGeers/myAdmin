# User & Role Management UI

## Overview

The User & Role Management interface provides system administrators with a clean, modal-based UI for managing users and their role assignments in AWS Cognito.

**Last Updated**: January 28, 2026

---

## Design Philosophy

### Before (Old Design)
- Inline role management with multiple buttons per row
- Limited actions: Add role, Enable/Disable, Delete
- Missing functionality: Remove role from user
- Cluttered interface with inline dropdowns
- No user creation capability

### After (New Design)
- Clean table with single "Manage" button per user
- Comprehensive modal for all user operations
- All CRUD operations in one place
- Add User button in header
- Checkbox-based role selection

---

## UI Components

### 1. Main Table View

**Location**: `frontend/src/components/SystemAdmin.tsx`

```
┌─────────────────────────────────────────────────────────────┐
│  User & Role Management                    [+ Add User]      │
├─────────────────────────────────────────────────────────────┤
│  Email          Status    Roles           Created   Actions │
│  ─────────────────────────────────────────────────────────  │
│  user@email.com CONFIRMED Finance_CRUD    1/15/26  [Manage] │
│                           Tenant_All                         │
│  admin@app.com  CONFIRMED System_CRUD     1/10/26  [Manage] │
│                           Tenant_All                         │
└─────────────────────────────────────────────────────────────┘
```

**Features**:
- Clean, read-only table display
- Role badges (non-interactive)
- Single "Manage" button per user
- "Add User" button in header

### 2. User Management Modal

**Triggered by**: Clicking "Manage" button on any user row

```
┌─────────────────────────────────────────────────────────────┐
│  Manage User: user@example.com                          [X] │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  User Status                                                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ [CONFIRMED]  Created: January 15, 2026                 │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  Manage Roles                                                │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ ☑ Finance_CRUD                                         │ │
│  │   Full financial data management                       │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │ ☐ Finance_Read                                         │ │
│  │   Read-only financial access                           │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │ ☑ Tenant_All                                           │ │
│  │   Access to all tenants                                │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │ ☐ STR_CRUD                                             │ │
│  │   Full short-term rental management                    │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  Danger Zone                                                 │
│  [Disable User]  [Delete User Permanently]                  │
│                                                              │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│                              [Cancel]  [Save Changes]        │
└─────────────────────────────────────────────────────────────┘
```

**Modal Sections**:

1. **User Status** (Read-only)
   - Current status badge
   - Creation date

2. **Manage Roles** (Interactive)
   - Checkbox list of all available roles
   - Role name and description
   - Visual indication of selected roles
   - Add/remove roles by checking/unchecking

3. **Danger Zone** (Destructive actions)
   - Disable/Enable user button
   - Delete user button

4. **Actions**
   - Cancel: Close without saving
   - Save Changes: Apply role modifications

### 3. Create User Modal

**Triggered by**: Clicking "Add User" button in header

```
┌─────────────────────────────────────────────────────────────┐
│  Create New User                                        [X] │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Email *                                                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ user@example.com                                       │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  Temporary Password *                                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ ••••••••                                               │ │
│  └────────────────────────────────────────────────────────┘ │
│  User will be required to change password on first login    │
│                                                              │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  Assign Roles                                                │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ ☐ Finance_CRUD                                         │ │
│  │   Full financial data management                       │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │ ☑ Finance_Read                                         │ │
│  │   Read-only financial access                           │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │ ☑ Tenant_PeterPrive                                    │ │
│  │   PeterPrive tenant access                             │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│                              [Cancel]  [Create User]         │
└─────────────────────────────────────────────────────────────┘
```

**Form Fields**:

1. **Email** (Required)
   - User's email address
   - Used as username in Cognito

2. **Temporary Password** (Required)
   - Minimum 8 characters
   - Must meet password policy
   - User forced to change on first login

3. **Assign Roles** (Optional)
   - Same checkbox interface as edit modal
   - Can assign multiple roles at creation

---

## User Operations

### 1. View Users
**Action**: Page load  
**Endpoint**: `GET /api/admin/users`  
**Response**: List of users with roles

### 2. Add Role to User
**Action**: Check role checkbox, click "Save Changes"  
**Endpoint**: `POST /api/admin/users/{username}/groups`  
**Body**: `{ "groupName": "Finance_CRUD" }`

### 3. Remove Role from User
**Action**: Uncheck role checkbox, click "Save Changes"  
**Endpoint**: `DELETE /api/admin/users/{username}/groups/{groupName}`

### 4. Create User
**Action**: Click "Add User", fill form, click "Create User"  
**Endpoint**: `POST /api/admin/users`  
**Body**:
```json
{
  "email": "user@example.com",
  "password": "TempPass123!",
  "groups": ["Finance_Read", "Tenant_PeterPrive"]
}
```

### 5. Disable User
**Action**: Click "Disable User" in modal  
**Endpoint**: `POST /api/admin/users/{username}/disable`

### 6. Enable User
**Action**: Click "Enable User" in modal  
**Endpoint**: `POST /api/admin/users/{username}/enable`

### 7. Delete User
**Action**: Click "Delete User Permanently" in modal  
**Endpoint**: `DELETE /api/admin/users/{username}`

---

## Backend Implementation

### Admin Routes

**Location**: `backend/src/admin_routes.py`

#### List Users
```python
@admin_bp.route('/users', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def list_users(user_email, user_roles):
    """List all users with their groups"""
    response = cognito_client.list_users(
        UserPoolId=USER_POOL_ID,
        Limit=60
    )
    # Returns users with groups array
```

#### Create User (NEW)
```python
@admin_bp.route('/users', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def create_user(user_email, user_roles):
    """Create new user with optional role assignments"""
    data = request.get_json()
    
    # Create user
    response = cognito_client.admin_create_user(
        UserPoolId=USER_POOL_ID,
        Username=email,
        UserAttributes=[
            {'Name': 'email', 'Value': email},
            {'Name': 'email_verified', 'Value': 'true'}
        ],
        TemporaryPassword=password,
        MessageAction='SUPPRESS'
    )
    
    # Add to groups
    for group_name in groups:
        cognito_client.admin_add_user_to_group(
            UserPoolId=USER_POOL_ID,
            Username=username,
            GroupName=group_name
        )
```

#### Add User to Group
```python
@admin_bp.route('/users/<username>/groups', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def add_user_to_group(username, user_email, user_roles):
    """Assign role to user"""
    cognito_client.admin_add_user_to_group(
        UserPoolId=USER_POOL_ID,
        Username=username,
        GroupName=group_name
    )
```

#### Remove User from Group
```python
@admin_bp.route('/users/<username>/groups/<group_name>', methods=['DELETE'])
@cognito_required(required_roles=['SysAdmin'])
def remove_user_from_group(username, group_name, user_email, user_roles):
    """Remove role from user"""
    cognito_client.admin_remove_user_from_group(
        UserPoolId=USER_POOL_ID,
        Username=username,
        GroupName=group_name
    )
```

#### Enable/Disable User
```python
@admin_bp.route('/users/<username>/enable', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def enable_user(username, user_email, user_roles):
    """Enable user account"""
    cognito_client.admin_enable_user(
        UserPoolId=USER_POOL_ID,
        Username=username
    )

@admin_bp.route('/users/<username>/disable', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def disable_user(username, user_email, user_roles):
    """Disable user account"""
    cognito_client.admin_disable_user(
        UserPoolId=USER_POOL_ID,
        Username=username
    )
```

#### Delete User
```python
@admin_bp.route('/users/<username>', methods=['DELETE'])
@cognito_required(required_roles=['SysAdmin'])
def delete_user(username, user_email, user_roles):
    """Permanently delete user"""
    cognito_client.admin_delete_user(
        UserPoolId=USER_POOL_ID,
        Username=username
    )
```

---

## Frontend Implementation

### Component Structure

**Location**: `frontend/src/components/SystemAdmin.tsx`

```typescript
interface User {
  username: string;
  email: string;
  status: string;
  enabled: boolean;
  groups: string[];
  created: string;
}

interface Group {
  name: string;
  description: string;
  precedence: number;
}

export default function SystemAdmin() {
  const [users, setUsers] = useState<User[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [modalMode, setModalMode] = useState<'edit' | 'create'>('edit');
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  
  // Modal operations
  const openEditModal = (user: User) => { /* ... */ };
  const openCreateModal = () => { /* ... */ };
  const handleSaveUser = async () => { /* ... */ };
  const toggleRole = (roleName: string) => { /* ... */ };
  
  // User operations
  const createUser = async () => { /* ... */ };
  const updateUserRoles = async () => { /* ... */ };
  const toggleUserStatus = async (enable: boolean) => { /* ... */ };
  const deleteUser = async () => { /* ... */ };
}
```

### Key Features

1. **Single Modal for All Operations**
   - Edit mode: Manage existing user
   - Create mode: Add new user
   - Same role selection interface

2. **Checkbox-Based Role Selection**
   - Visual indication of assigned roles
   - Easy to add/remove multiple roles
   - Shows role descriptions

3. **Batch Role Updates**
   - Compares initial vs final role selection
   - Adds new roles
   - Removes unchecked roles
   - Single "Save Changes" action

4. **Error Handling**
   - Toast notifications for success/error
   - Validation before submission
   - Clear error messages

---

## User Experience Flow

### Editing User Roles

1. Admin clicks "Manage" button on user row
2. Modal opens with current roles checked
3. Admin checks/unchecks roles as needed
4. Admin clicks "Save Changes"
5. System adds new roles and removes unchecked roles
6. Toast notification confirms success
7. Modal closes, table refreshes

### Creating New User

1. Admin clicks "Add User" button
2. Create modal opens
3. Admin enters email and temporary password
4. Admin selects initial roles (optional)
5. Admin clicks "Create User"
6. System creates user in Cognito
7. System assigns selected roles
8. Toast notification confirms success
9. Modal closes, table refreshes with new user

### Disabling User

1. Admin opens user management modal
2. Admin clicks "Disable User" in Danger Zone
3. System disables user account
4. Toast notification confirms success
5. Modal closes, table shows updated status

---

## Security Considerations

### Authorization

- All endpoints require `SysAdmin` role
- JWT token validation on every request
- Role-based access control enforced

### Password Policy

- Minimum 8 characters
- Requires uppercase, lowercase, numbers, symbols
- Temporary password must be changed on first login

### Audit Trail

- All user management actions logged
- Includes: who, what, when, which user affected
- Stored in application logs

---

## Testing

### Manual Testing Checklist

- [ ] View users list
- [ ] Add role to user
- [ ] Remove role from user
- [ ] Create new user with roles
- [ ] Create new user without roles
- [ ] Disable user
- [ ] Enable user
- [ ] Delete user
- [ ] Cancel modal without saving
- [ ] Verify role changes persist
- [ ] Verify toast notifications appear
- [ ] Test with invalid email
- [ ] Test with weak password

### Edge Cases

- User with no roles
- User with all roles
- Creating duplicate user (should fail)
- Deleting currently logged-in user
- Removing last SysAdmin role (should warn)

---

## Future Enhancements

### Potential Improvements

1. **Bulk Operations**
   - Select multiple users
   - Assign role to multiple users at once
   - Bulk disable/enable

2. **Search and Filter**
   - Search users by email
   - Filter by role
   - Filter by status

3. **Role Templates**
   - Predefined role combinations
   - Quick assign common role sets

4. **User Invitation**
   - Send email invitation
   - User sets own password
   - Welcome email with instructions

5. **Activity Log**
   - Show recent user management actions
   - Who made changes and when
   - Audit trail in UI

---

## Related Documentation

- [Implementation Guide](./implementation-guide.md) - Overall Cognito architecture
- [Setup Guide](./setup-guide.md) - Initial Cognito configuration
- [RBAC Design](./implementation-guide.md#role-based-access-control-rbac-design) - Role structure

---

## Files Modified

### Frontend
- `frontend/src/components/SystemAdmin.tsx` - Complete UI redesign

### Backend
- `backend/src/admin_routes.py` - Added POST /users endpoint

### Dependencies
- Uses existing `@chakra-ui/icons` (no new dependencies)

---

## Summary

The redesigned User & Role Management UI provides a cleaner, more intuitive interface for managing users and roles. The modal-based approach consolidates all user operations in one place, making it easier to perform complex tasks like managing multiple role assignments. The addition of user creation capability completes the CRUD operations needed for full user lifecycle management.
