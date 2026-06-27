#!/bin/bash
# Bootstrap script: creates the S3 bucket for Terraform state
# Run this ONCE before running `terraform init -migrate-state`

BUCKET_NAME="myadmin-terraform-state-eu-west-1"
REGION="eu-west-1"

echo "Creating S3 bucket for Terraform state..."

# Create bucket
aws s3api create-bucket \
  --bucket "$BUCKET_NAME" \
  --region "$REGION" \
  --create-bucket-configuration LocationConstraint="$REGION"

# Enable versioning (so you can recover previous state versions)
aws s3api put-bucket-versioning \
  --bucket "$BUCKET_NAME" \
  --versioning-configuration Status=Enabled

# Enable server-side encryption
aws s3api put-bucket-encryption \
  --bucket "$BUCKET_NAME" \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'

# Block all public access
aws s3api put-public-access-block \
  --bucket "$BUCKET_NAME" \
  --public-access-block-configuration '{
    "BlockPublicAcls": true,
    "IgnorePublicAcls": true,
    "BlockPublicPolicy": true,
    "RestrictPublicBuckets": true
  }'

echo ""
echo "✅ Bucket created: $BUCKET_NAME"
echo ""
echo "Next steps:"
echo "  1. cd infrastructure/"
echo "  2. terraform init -migrate-state"
echo "  3. Type 'yes' when prompted to copy state to S3"
echo "  4. Verify: terraform plan (should show no changes)"
echo "  5. Delete local terraform.tfstate (S3 is now the source of truth)"
