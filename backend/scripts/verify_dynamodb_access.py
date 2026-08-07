"""
Verify DynamoDB Access for Landing Pages

Connectivity test script that validates boto3 can access the
`myadmin-landing-pages` DynamoDB table from the Railway environment.

Steps:
1. Describe the table (confirms table exists and credentials work)
2. Put a test item (confirms write access)
3. Get the test item (confirms read access and data integrity)
4. Delete the test item (confirms delete access and cleans up)

Usage:
    python scripts/verify_dynamodb_access.py

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
"""

import os
import sys
from pathlib import Path

# Add backend/src to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir / "src"))

# Load environment variables from .env file if available
from dotenv import load_dotenv

env_path = backend_dir / ".env"
if env_path.exists():
    load_dotenv(env_path)

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError

TABLE_NAME = "myadmin-landing-pages"
TEST_PK = "TEST#connectivity"
TEST_SK = "VERIFY#1"


def get_region():
    """Get AWS region from environment with eu-west-1 fallback."""
    return os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")


def check_credentials():
    """Verify AWS credentials are available in the environment."""
    print("Step 0: Checking AWS credentials...")

    key_id = os.environ.get("AWS_ACCESS_KEY_ID")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY")

    if not key_id:
        print("  ✗ AWS_ACCESS_KEY_ID not set")
        return False
    if not secret:
        print("  ✗ AWS_SECRET_ACCESS_KEY not set")
        return False

    # Mask credentials for display
    print(f"  AWS_ACCESS_KEY_ID: {key_id[:4]}...{key_id[-4:]}")
    print(f"  AWS_SECRET_ACCESS_KEY: ****{secret[-4:]}")
    print(f"  AWS_DEFAULT_REGION: {get_region()}")
    print("  ✓ Credentials present")
    return True


def describe_table(dynamodb_client):
    """Verify the table exists and is active."""
    print(f"\nStep 1: Describing table '{TABLE_NAME}'...")

    try:
        response = dynamodb_client.describe_table(TableName=TABLE_NAME)
        table = response["Table"]
        status = table["TableStatus"]
        item_count = table.get("ItemCount", 0)
        key_schema = table.get("KeySchema", [])

        print(f"  Table status: {status}")
        print(f"  Item count: {item_count}")
        print(f"  Key schema: {key_schema}")

        if status == "ACTIVE":
            print("  ✓ Table is active and accessible")
            return True
        else:
            print(f"  ✗ Table is not active (status: {status})")
            return False

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = e.response["Error"]["Message"]
        print(f"  ✗ ClientError ({error_code}): {error_msg}")
        return False
    except EndpointConnectionError as e:
        print(f"  ✗ Cannot connect to DynamoDB endpoint: {e}")
        return False


def put_test_item(dynamodb_resource):
    """Write a test item to verify put access."""
    print(f"\nStep 2: Writing test item (PK={TEST_PK}, SK={TEST_SK})...")

    try:
        table = dynamodb_resource.Table(TABLE_NAME)
        table.put_item(
            Item={
                "PK": TEST_PK,
                "SK": TEST_SK,
                "test_field": "connectivity_check",
                "source": "verify_dynamodb_access.py",
            }
        )
        print("  ✓ PutItem succeeded")
        return True

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = e.response["Error"]["Message"]
        print(f"  ✗ ClientError ({error_code}): {error_msg}")
        return False


def get_test_item(dynamodb_resource):
    """Read the test item back and verify values match."""
    print(f"\nStep 3: Reading test item back...")

    try:
        table = dynamodb_resource.Table(TABLE_NAME)
        response = table.get_item(Key={"PK": TEST_PK, "SK": TEST_SK})

        item = response.get("Item")
        if not item:
            print("  ✗ Item not found after put")
            return False

        # Verify field values
        if item.get("PK") != TEST_PK:
            print(f"  ✗ PK mismatch: expected '{TEST_PK}', got '{item.get('PK')}'")
            return False
        if item.get("SK") != TEST_SK:
            print(f"  ✗ SK mismatch: expected '{TEST_SK}', got '{item.get('SK')}'")
            return False
        if item.get("test_field") != "connectivity_check":
            print(f"  ✗ test_field mismatch: got '{item.get('test_field')}'")
            return False

        print(f"  PK: {item['PK']}")
        print(f"  SK: {item['SK']}")
        print(f"  test_field: {item['test_field']}")
        print("  ✓ GetItem succeeded — values match")
        return True

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = e.response["Error"]["Message"]
        print(f"  ✗ ClientError ({error_code}): {error_msg}")
        return False


def delete_test_item(dynamodb_resource):
    """Delete the test item to clean up."""
    print(f"\nStep 4: Deleting test item...")

    try:
        table = dynamodb_resource.Table(TABLE_NAME)
        table.delete_item(Key={"PK": TEST_PK, "SK": TEST_SK})
        print("  ✓ DeleteItem succeeded — cleanup complete")
        return True

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = e.response["Error"]["Message"]
        print(f"  ✗ ClientError ({error_code}): {error_msg}")
        return False


def main():
    """Run all DynamoDB connectivity checks."""
    print("=" * 55)
    print("  DynamoDB Connectivity Test — myadmin-landing-pages")
    print("=" * 55)
    print()

    # Check credentials first
    if not check_credentials():
        print("\n" + "=" * 55)
        print("  RESULT: FAILED — missing AWS credentials")
        print("=" * 55)
        sys.exit(1)

    region = get_region()

    try:
        dynamodb_client = boto3.client("dynamodb", region_name=region)
        dynamodb_resource = boto3.resource("dynamodb", region_name=region)
    except NoCredentialsError:
        print("\n  ✗ boto3 cannot find valid AWS credentials")
        print("    Ensure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are set")
        sys.exit(1)

    # Run checks
    results = []

    results.append(("Describe table", describe_table(dynamodb_client)))
    results.append(("Put item", put_test_item(dynamodb_resource)))
    results.append(("Get item", get_test_item(dynamodb_resource)))
    results.append(("Delete item", delete_test_item(dynamodb_resource)))

    # Summary
    print("\n" + "=" * 55)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    for name, ok in results:
        status = "✓" if ok else "✗"
        print(f"  {status} {name}")

    print()
    if passed == total:
        print(f"  RESULT: ALL PASSED ({passed}/{total})")
        print("  DynamoDB access from this environment is working.")
    else:
        print(f"  RESULT: FAILED ({passed}/{total} passed)")
        print("  Check the errors above for details.")

    print("=" * 55)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
