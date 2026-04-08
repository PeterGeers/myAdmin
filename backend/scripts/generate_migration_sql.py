"""Generate SQL INSERT statements for Railway migration."""
import boto3
import json
import os

os.environ['AWS_DEFAULT_REGION'] = 'eu-west-1'
client = boto3.client('cognito-idp', region_name='eu-west-1')
pool_id = 'eu-west-1_Hdp40eWmu'
GLOBAL_ROLES = {'SysAdmin', 'Administrators', 'System_CRUD'}

users = client.list_users(UserPoolId=pool_id, Limit=60)
statements = []

for u in users['Users']:
    email = next((a['Value'] for a in u['Attributes'] if a['Name'] == 'email'), u['Username'])
    tenants_raw = next((a['Value'] for a in u['Attributes'] if a['Name'] == 'custom:tenants'), '[]')
    try:
        tenants = json.loads(tenants_raw)
    except (json.JSONDecodeError, TypeError):
        tenants = [tenants_raw] if tenants_raw else []
    groups_resp = client.admin_list_groups_for_user(Username=u['Username'], UserPoolId=pool_id)
    roles = [g['GroupName'] for g in groups_resp['Groups'] if g['GroupName'] not in GLOBAL_ROLES]

    for tenant in tenants:
        for role in roles:
            stmt = f"INSERT IGNORE INTO user_tenant_roles (email, administration, role, created_by) VALUES ('{email}', '{tenant}', '{role}', 'migration');"
            statements.append(stmt)

print('-- Per-tenant roles migration')
print(f'-- {len(statements)} statements')
print()
for s in statements:
    print(s)
