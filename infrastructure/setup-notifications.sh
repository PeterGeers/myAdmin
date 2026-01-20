#!/bin/bash
# AWS Notifications Setup Script
# This script helps set up AWS SNS notifications for myAdmin

set -e

echo "========================================="
echo "AWS Notifications Setup for myAdmin"
echo "========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}✗ AWS CLI is not installed${NC}"
    echo "Please install AWS CLI first:"
    echo "  https://aws.amazon.com/cli/"
    exit 1
fi

echo -e "${GREEN}✓ AWS CLI is installed${NC}"

# Check if Terraform is installed
if ! command -v terraform &> /dev/null; then
    echo -e "${RED}✗ Terraform is not installed${NC}"
    echo "Please install Terraform first:"
    echo "  https://www.terraform.io/downloads"
    exit 1
fi

echo -e "${GREEN}✓ Terraform is installed${NC}"

# Check AWS credentials
echo ""
echo "Checking AWS credentials..."
if aws sts get-caller-identity &> /dev/null; then
    echo -e "${GREEN}✓ AWS credentials are configured${NC}"
    aws sts get-caller-identity
else
    echo -e "${RED}✗ AWS credentials are not configured${NC}"
    echo "Please run: aws configure"
    exit 1
fi

# Get user input
echo ""
echo "========================================="
echo "Configuration"
echo "========================================="
echo ""

read -p "Enter your AWS region [eu-west-1]: " AWS_REGION
AWS_REGION=${AWS_REGION:-eu-west-1}

read -p "Enter your EC2 key pair name: " KEY_NAME
if [ -z "$KEY_NAME" ]; then
    echo -e "${RED}✗ Key pair name is required${NC}"
    exit 1
fi

read -p "Enter admin email address [peter@pgeers.nl]: " ADMIN_EMAIL
ADMIN_EMAIL=${ADMIN_EMAIL:-peter@pgeers.nl}

read -p "Enter domain name [admin.pgeers.nl]: " DOMAIN_NAME
DOMAIN_NAME=${DOMAIN_NAME:-admin.pgeers.nl}

# Create terraform.tfvars
echo ""
echo "Creating terraform.tfvars..."
cat > terraform.tfvars <<EOF
# AWS Configuration
aws_region = "$AWS_REGION"
key_name   = "$KEY_NAME"
domain_name = "$DOMAIN_NAME"

# Notification Configuration
admin_email = "$ADMIN_EMAIL"

# Optional: Add more email addresses
additional_notification_emails = []
EOF

echo -e "${GREEN}✓ terraform.tfvars created${NC}"

# Initialize Terraform
echo ""
echo "Initializing Terraform..."
terraform init

# Plan
echo ""
echo "========================================="
echo "Terraform Plan"
echo "========================================="
echo ""
terraform plan

# Ask for confirmation
echo ""
read -p "Do you want to apply these changes? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Setup cancelled"
    exit 0
fi

# Apply
echo ""
echo "Applying Terraform configuration..."
terraform apply -auto-approve

# Get outputs
echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""

SNS_TOPIC_ARN=$(terraform output -raw sns_topic_arn 2>/dev/null || echo "")
INSTANCE_IP=$(terraform output -raw instance_ip 2>/dev/null || echo "")

if [ -n "$SNS_TOPIC_ARN" ]; then
    echo -e "${GREEN}✓ SNS Topic created${NC}"
    echo "  ARN: $SNS_TOPIC_ARN"
fi

if [ -n "$INSTANCE_IP" ]; then
    echo -e "${GREEN}✓ EC2 Instance ready${NC}"
    echo "  IP: $INSTANCE_IP"
fi

# Instructions
echo ""
echo "========================================="
echo "Next Steps"
echo "========================================="
echo ""
echo "1. ${YELLOW}IMPORTANT:${NC} Check your email ($ADMIN_EMAIL)"
echo "   Look for 'AWS Notification - Subscription Confirmation'"
echo "   Click the confirmation link"
echo ""
echo "2. Test the notification:"
echo "   aws sns publish \\"
echo "     --topic-arn $SNS_TOPIC_ARN \\"
echo "     --message 'Test from myAdmin' \\"
echo "     --subject 'Test Notification' \\"
echo "     --region $AWS_REGION"
echo ""
echo "3. Configure your application:"
echo "   Add to backend/.env:"
echo "   SNS_TOPIC_ARN=$SNS_TOPIC_ARN"
echo "   AWS_REGION=$AWS_REGION"
echo ""
echo "4. Install boto3 on your EC2 instance:"
echo "   ssh -i $KEY_NAME.pem ec2-user@$INSTANCE_IP"
echo "   cd /path/to/myAdmin/backend"
echo "   source venv/bin/activate"
echo "   pip install boto3"
echo ""
echo "Setup script completed!"
echo ""
