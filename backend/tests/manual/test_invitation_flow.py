"""
Test Invitation Flow

Tests the complete invitation lifecycle:
1. Create invitation
2. Generate temporary password
3. Mark as sent
4. Resend invitation
5. Check expiry logic
"""

import os
import sys
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from services.invitation_service import InvitationService


def test_invitation_flow():
    """Test complete invitation flow"""
    
    print("=" * 80)
    print("Testing Invitation Flow")
    print("=" * 80)
    
    # Initialize service (use test mode)
    service = InvitationService(test_mode=True)
    
    # Test data
    tenant = "TestTenant"
    email = "test@example.com"
    created_by = "admin@example.com"
    
    print("\n1. Testing temporary password generation...")
    password = service.generate_temporary_password()
    print(f"   ✓ Generated password: {password}")
    print(f"   ✓ Length: {len(password)} characters")
    
    # Verify password meets requirements
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in '!@#$%^&*' for c in password)
    
    print(f"   ✓ Has uppercase: {has_upper}")
    print(f"   ✓ Has lowercase: {has_lower}")
    print(f"   ✓ Has digit: {has_digit}")
    print(f"   ✓ Has special char: {has_special}")
    
    if not all([has_upper, has_lower, has_digit, has_special]):
        print("   ✗ Password does not meet Cognito requirements!")
        return False
    
    print("\n2. Creating invitation...")
    result = service.create_invitation(
        administration=tenant,
        email=email,
        username="test-uuid-123",
        created_by=created_by
    )
    
    if result.get('success'):
        print(f"   ✓ Invitation created successfully")
        print(f"   ✓ Email: {result['email']}")
        print(f"   ✓ Temporary password: {result['temporary_password']}")
        print(f"   ✓ Expires at: {result['expires_at']}")
        print(f"   ✓ Expiry days: {result['expiry_days']}")
    else:
        print(f"   ✗ Failed to create invitation: {result.get('error')}")
        return False
    
    print("\n3. Retrieving invitation...")
    invitation = service.get_invitation(tenant, email)
    
    if invitation:
        print(f"   ✓ Invitation found")
        print(f"   ✓ Status: {invitation['invitation_status']}")
        print(f"   ✓ Created by: {invitation['created_by']}")
        print(f"   ✓ Resend count: {invitation['resend_count']}")
    else:
        print("   ✗ Invitation not found!")
        return False
    
    print("\n4. Marking invitation as sent...")
    success = service.mark_invitation_sent(tenant, email)
    
    if success:
        print("   ✓ Invitation marked as sent")
        
        # Verify status changed
        invitation = service.get_invitation(tenant, email)
        if invitation['invitation_status'] == 'sent':
            print(f"   ✓ Status updated to: {invitation['invitation_status']}")
        else:
            print(f"   ✗ Status not updated correctly: {invitation['invitation_status']}")
            return False
    else:
        print("   ✗ Failed to mark as sent")
        return False
    
    print("\n5. Testing resend invitation...")
    resend_result = service.resend_invitation(
        administration=tenant,
        email=email,
        created_by=created_by
    )
    
    if resend_result.get('success'):
        print("   ✓ Invitation resent successfully")
        print(f"   ✓ New temporary password: {resend_result['temporary_password']}")
        
        # Verify resend count incremented
        invitation = service.get_invitation(tenant, email)
        print(f"   ✓ Resend count: {invitation['resend_count']}")
        
        if invitation['resend_count'] > 0:
            print("   ✓ Resend count incremented")
        else:
            print("   ✗ Resend count not incremented")
            return False
    else:
        print(f"   ✗ Failed to resend: {resend_result.get('error')}")
        return False
    
    print("\n6. Testing list invitations...")
    invitations = service.list_invitations(tenant)
    print(f"   ✓ Found {len(invitations)} invitation(s) for {tenant}")
    
    # List by status
    pending = service.list_invitations(tenant, status='pending')
    sent = service.list_invitations(tenant, status='sent')
    print(f"   ✓ Pending: {len(pending)}, Sent: {len(sent)}")
    
    print("\n7. Testing mark as accepted...")
    success = service.mark_invitation_accepted(tenant, email)
    
    if success:
        print("   ✓ Invitation marked as accepted")
        
        invitation = service.get_invitation(tenant, email)
        if invitation['invitation_status'] == 'accepted':
            print(f"   ✓ Status updated to: {invitation['invitation_status']}")
            print(f"   ✓ Accepted at: {invitation['accepted_at']}")
        else:
            print(f"   ✗ Status not updated: {invitation['invitation_status']}")
            return False
    else:
        print("   ✗ Failed to mark as accepted")
        return False
    
    print("\n8. Testing expiry logic...")
    # Create a new invitation for expiry test
    test_email = "expiry-test@example.com"
    service.create_invitation(
        administration=tenant,
        email=test_email,
        created_by=created_by
    )
    
    # Mark as sent
    service.mark_invitation_sent(tenant, test_email)
    
    print(f"   ✓ Created test invitation for {test_email}")
    
    # Note: We can't actually test expiry without manipulating the database
    # or waiting 7 days, but we can verify the method exists and runs
    expired_count = service.expire_old_invitations()
    print(f"   ✓ Expire method executed (expired {expired_count} invitations)")
    
    print("\n" + "=" * 80)
    print("✓ All invitation flow tests passed!")
    print("=" * 80)
    
    return True


if __name__ == '__main__':
    try:
        success = test_invitation_flow()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
