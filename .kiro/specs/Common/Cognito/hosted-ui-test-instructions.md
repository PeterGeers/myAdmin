# Cognito Hosted UI Test Instructions

## Task 1.3: Test Hosted UI

### Your Cognito Configuration

- **User Pool ID**: `eu-west-1_Hdp40eWmu`
- **Client ID**: `6sgh53un5ttsojn7o2aj9hi7en`
- **Domain**: `myadmin-6x2848jl`
- **Region**: `eu-west-1`

### Step 1: Visit the Hosted UI

Open your web browser and navigate to this URL:

```
https://myadmin-6x2848jl.auth.eu-west-1.amazoncognito.com/login?client_id=6sgh53un5ttsojn7o2aj9hi7en&response_type=code&redirect_uri=http://localhost:3000/callback
```

**Direct clickable link**: https://myadmin-6x2848jl.auth.eu-west-1.amazoncognito.com/login?client_id=6sgh53un5ttsojn7o2aj9hi7en&response_type=code&redirect_uri=http://localhost:3000/callback

### Step 2: Login with Admin Credentials

Use the admin credentials that were created in Task 1.2:

- **Email**: `peter@pgeers.nl`
- **Password**: (The password you set when creating the user)

### Step 3: Verify JWT Token

After successful login, you'll be redirected to `http://localhost:3000/callback` with an authorization code in the URL.

To verify the JWT token contains the correct groups:

1. **Open Browser Developer Console** (F12)
2. **Go to the Network tab** before logging in
3. After login, look for the token exchange request
4. Copy the `id_token` from the response
5. **Decode the token** at https://jwt.io
6. **Verify the payload** contains:
   ```json
   {
     "cognito:groups": ["Administrators"],
     "email": "peter@pgeers.nl",
     ...
   }
   ```

### Alternative: Get Token via AWS CLI

You can also get a token directly using AWS CLI:

```powershell
# Initiate auth (you'll need the password)
aws cognito-idp admin-initiate-auth `
    --user-pool-id eu-west-1_Hdp40eWmu `
    --client-id 6sgh53un5ttsojn7o2aj9hi7en `
    --auth-flow ADMIN_NO_SRP_AUTH `
    --auth-parameters USERNAME=peter@pgeers.nl,PASSWORD=<YOUR_PASSWORD> `
    --region eu-west-1
```

### Expected Results

✅ **Success Criteria**:

- Hosted UI loads without errors
- Login form is displayed
- Login with admin credentials succeeds
- Redirect to callback URL occurs
- JWT token contains `cognito:groups` with `["Administrators"]`

❌ **Common Issues**:

- **Redirect URI mismatch**: Ensure `http://localhost:3000/callback` is configured in Cognito App Client settings
- **User not confirmed**: User might need to be confirmed first
- **Wrong password**: Check the password set during user creation

### Verification Checklist

- [ ] Hosted UI accessible at the URL above
- [ ] Login form displays correctly
- [ ] Login with `peter@pgeers.nl` succeeds
- [ ] Redirect to callback URL occurs
- [ ] JWT token decoded successfully
- [ ] Token contains `cognito:groups: ["Administrators"]`
- [ ] Token contains correct email address

### Next Steps

Once verified, update the task status in `tasks.md` and proceed to Phase 2: Backend Integration.
