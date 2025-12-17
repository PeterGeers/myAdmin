# myAdmin AWS Migration Plan

## Overview
Migrate myAdmin from localhost to AWS production environment with containerized backend and Amplify frontend.

## Target Architecture
- **Backend**: t3.small EC2 with Docker containers (Flask + MySQL)
- **Frontend**: AWS Amplify with GitHub integration
- **Domain**: admin.pgeers.nl (DNS at GoDaddy)
- **Auth**: Basic HTTP Auth with nginx

---

## Phase 1: Setup Infrastructure as Code (Terraform)

### Step 1.1: Install and Configure Terraform
```bash
# Install Terraform
choco install terraform  # Windows
# Or download from https://terraform.io/downloads

# Verify installation
terraform version
```

### Step 1.2: Setup AWS Credentials
```bash
# Configure AWS CLI
aws configure
# Enter: Access Key, Secret Key, Region (eu-west-1)
# Note: Use eu-west-1 (Ireland) for cost optimization and scope

# Create EC2 key pair
aws ec2 create-key-pair --key-name myAdmin-key --query 'KeyMaterial' --output text > myAdmin-key.pem
chmod 400 myAdmin-key.pem  # Linux/Mac
# Windows: Right-click -> Properties -> Security -> Advanced
```

### Step 1.3: Create Infrastructure Directory
```bash
# Create infrastructure folder structure
mkdir infrastructure
cd infrastructure

# Create Terraform configuration files
# (Use the Terraform code from Phase 3 below)
```

### Step 1.4: Initialize Terraform
```bash
# Initialize Terraform
terraform init

# Validate configuration
terraform validate

# Plan deployment (dry run)
terraform plan -var="key_name=myAdmin-key"
```

**✅ Checkpoint**: Terraform configured and ready to deploy

---

## Phase 2: Prepare Backend for Containerization

### Step 1.1: Create Docker Configuration
```dockerfile
# backend/Dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "app.py"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_PASSWORD}
      MYSQL_DATABASE: ${DB_NAME}
    volumes:
      - mysql_data:/var/lib/mysql
    mem_limit: 512m
    
  backend:
    build: ./backend
    ports:
      - "5000:5000"
    depends_on:
      - mysql
    environment:
      - DB_HOST=mysql
      - DB_NAME=${DB_NAME}
      - DB_PASSWORD=${DB_PASSWORD}
    mem_limit: 1g

volumes:
  mysql_data:
```

### Step 1.2: Update Backend Configuration
```python
# backend/src/config.py
import os

class Config:
    # Database - use container hostname
    DB_HOST = os.getenv('DB_HOST', 'mysql')  # Changed from localhost
    DB_NAME = os.getenv('DB_NAME', 'finance')
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    
    # API URLs - use relative paths
    API_BASE_URL = os.getenv('API_BASE_URL', '')
```

### Step 1.3: Test Locally
```bash
# Test containers locally
docker-compose up --build
# Verify: http://localhost:5000/api/status
```

**✅ Checkpoint**: Backend runs in containers locally

---

## Phase 3: Prepare Frontend for Amplify

### Step 2.1: Update API URLs
```typescript
// frontend/src/config.ts
const config = {
  API_BASE_URL: process.env.NODE_ENV === 'production' 
    ? 'https://admin.pgeers.nl/api'  // Production API
    : 'http://localhost:5000',       // Development API
};

export default config;
```

### Step 2.2: Update All API Calls
```typescript
// Replace all instances of 'http://localhost:5000' with config.API_BASE_URL
// Example in PDFUploadForm.tsx:
import config from '../config';

const response = await axios.post(`${config.API_BASE_URL}/api/upload`, formData);
```

### Step 2.3: Create Amplify Configuration
```yaml
# amplify.yml
version: 1
frontend:
  phases:
    preBuild:
      commands:
        - npm ci
    build:
      commands:
        - npm run build
  artifacts:
    baseDirectory: build
    files:
      - '**/*'
  cache:
    paths:
      - node_modules/**/*
```

### Step 2.4: Test Frontend Locally
```bash
cd frontend
npm start
# Verify: http://localhost:3000 (should fail API calls - expected)
```

**✅ Checkpoint**: Frontend builds successfully

---

## Phase 4: Deploy Backend Infrastructure (IaC)

### Step 3.1: Create Terraform Configuration
```hcl
# infrastructure/main.tf
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Variables
variable "aws_region" {
  default = "eu-central-1"
}

variable "key_name" {
  description = "EC2 Key Pair name"
  type        = string
}

variable "domain_name" {
  default = "admin.pgeers.nl"
}

# Security Group
resource "aws_security_group" "myadmin_sg" {
  name_prefix = "myadmin-"
  description = "Security group for myAdmin application"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# EC2 Instance
resource "aws_instance" "myadmin_backend" {
  ami           = "ami-0c02fb55956c7d316"  # Amazon Linux 2
  instance_type = "t3.small"
  key_name      = var.key_name
  
  vpc_security_group_ids = [aws_security_group.myadmin_sg.id]
  
  user_data = base64encode(templatefile("${path.module}/user-data.sh", {
    domain_name = var.domain_name
  }))
  
  tags = {
    Name = "myAdmin-Backend"
    Environment = "Production"
  }
}

# Elastic IP
resource "aws_eip" "myadmin_eip" {
  instance = aws_instance.myadmin_backend.id
  domain   = "vpc"
  
  tags = {
    Name = "myAdmin-EIP"
  }
}

# Outputs
output "instance_ip" {
  value = aws_eip.myadmin_eip.public_ip
}

output "instance_dns" {
  value = aws_instance.myadmin_backend.public_dns
}

output "ssh_command" {
  value = "ssh -i ${var.key_name}.pem ec2-user@${aws_eip.myadmin_eip.public_ip}"
}
```

```bash
# infrastructure/user-data.sh
#!/bin/bash
yum update -y
yum install -y docker nginx git

# Start services
systemctl start docker
systemctl enable docker
systemctl start nginx
systemctl enable nginx

# Add ec2-user to docker group
usermod -a -G docker ec2-user

# Install docker-compose
curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Install certbot
yum install -y certbot python3-certbot-nginx

# Create nginx config
cat > /etc/nginx/conf.d/myadmin.conf << 'EOF'
server {
    listen 80;
    server_name ${domain_name};
    
    location /api/ {
        auth_basic "myAdmin API Access";
        auth_basic_user_file /etc/nginx/.htpasswd;
        
        proxy_pass http://localhost:5000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    location / {
        return 301 https://${domain_name}$request_uri;
    }
}
EOF

# Restart nginx
systemctl restart nginx
```

### Step 3.2: Deploy Infrastructure
```bash
# Initialize and deploy
cd infrastructure
terraform init
terraform plan -var="key_name=your-key-pair"
terraform apply -var="key_name=your-key-pair"

# Note the output IP address
terraform output instance_ip
```

### Step 3.3: Deploy Application with Ansible
```yaml
# infrastructure/deploy.yml
---
- hosts: myadmin_backend
  become: yes
  vars:
    app_user: ec2-user
    app_dir: /home/ec2-user/myAdmin
    db_password: "{{ vault_db_password }}"
    basic_auth_password: "{{ vault_basic_auth_password }}"
    
  tasks:
    - name: Clone repository
      git:
        repo: https://github.com/PeterGeers/myAdmin.git
        dest: "{{ app_dir }}"
        force: yes
      become_user: "{{ app_user }}"
      
    - name: Create .env file
      template:
        src: env.j2
        dest: "{{ app_dir }}/.env"
        owner: "{{ app_user }}"
        mode: '0600'
        
    - name: Create basic auth file
      htpasswd:
        path: /etc/nginx/.htpasswd
        name: admin
        password: "{{ basic_auth_password }}"
        
    - name: Start containers
      docker_compose:
        project_src: "{{ app_dir }}"
        state: present
      become_user: "{{ app_user }}"
      
    - name: Setup SSL certificate
      command: certbot --nginx -d admin.pgeers.nl --non-interactive --agree-tos --email peter@pgeers.nl
      
    - name: Setup certbot renewal
      cron:
        name: "Certbot renewal"
        minute: "0"
        hour: "12"
        job: "/usr/bin/certbot renew --quiet"
```

```jinja2
# infrastructure/templates/env.j2
DB_NAME=finance
DB_PASSWORD={{ db_password }}
TEST_MODE=false
OPENROUTER_API_KEY={{ openrouter_api_key }}
FACTUREN_FOLDER_ID={{ facturen_folder_id }}
```

```ini
# infrastructure/inventory.ini
[myadmin_backend]
{{ terraform_output_ip }} ansible_user=ec2-user ansible_ssh_private_key_file=your-key.pem
```

```bash
# Deploy application
ansible-playbook -i inventory.ini deploy.yml --ask-vault-pass
```



### Step 3.4: Test Backend API
```bash
# Test from your laptop
curl -u admin:password http://$(terraform output -raw instance_ip)/api/status
```

**✅ Checkpoint**: Backend API accessible via domain

---

## Phase 5: Deploy Frontend to Amplify (IaC)

### Step 4.0: Add Amplify to Terraform
```hcl
# Add to infrastructure/main.tf

# Amplify App
resource "aws_amplify_app" "myadmin_frontend" {
  name       = "myAdmin-Frontend"
  repository = "https://github.com/PeterGeers/myAdmin"
  
  # Build settings
  build_spec = "amplify.yml"
  
  # Environment variables
  environment_variables = {
    REACT_APP_API_BASE_URL = "https://${var.domain_name}/api"
    NODE_ENV = "production"
  }
  
  # Custom rules
  custom_rule {
    source = "/<*>"
    status = "404"
    target = "/index.html"
  }
  
  tags = {
    Name = "myAdmin-Frontend"
    Environment = "Production"
  }
}

# Amplify Branch
resource "aws_amplify_branch" "main" {
  app_id      = aws_amplify_app.myadmin_frontend.id
  branch_name = "main"
  
  framework = "React"
  stage     = "PRODUCTION"
}

# Amplify Domain
resource "aws_amplify_domain_association" "myadmin_domain" {
  app_id      = aws_amplify_app.myadmin_frontend.id
  domain_name = var.domain_name
  
  sub_domain {
    branch_name = aws_amplify_branch.main.branch_name
    prefix      = ""
  }
}

# Output Amplify URL
output "amplify_url" {
  value = "https://${aws_amplify_branch.main.branch_name}.${aws_amplify_app.myadmin_frontend.default_domain}"
}

output "amplify_custom_domain" {
  value = "https://${var.domain_name}"
}
```

### Step 4.1: Deploy Amplify with Terraform
```bash
# Update Terraform configuration
terraform plan -var="key_name=your-key-pair"
terraform apply -var="key_name=your-key-pair"

# Get Amplify URL
terraform output amplify_url
```

### Step 4.2: Connect GitHub Repository
```bash
# You'll need to manually connect GitHub in AWS Console first time
# Or use GitHub token in Terraform:
```

```hcl
# Add to main.tf for GitHub integration
resource "aws_amplify_app" "myadmin_frontend" {
  name       = "myAdmin-Frontend"
  repository = "https://github.com/PeterGeers/myAdmin"
  
  # GitHub access token (store in AWS Secrets Manager)
  access_token = data.aws_secretsmanager_secret_version.github_token.secret_string
  
  # ... rest of configuration
}

data "aws_secretsmanager_secret" "github_token" {
  name = "github-access-token"
}

data "aws_secretsmanager_secret_version" "github_token" {
  secret_id = data.aws_secretsmanager_secret.github_token.id
}
```

**✅ Checkpoint**: Frontend deployed on Amplify

---

## Phase 6: Configure DNS and SSL (Automated)

### Step 5.1: Get DNS Records from Terraform
```bash
# Get the required DNS records
terraform output

# Output will show:
# - Backend IP for A record
# - Amplify CNAME for frontend
```

### Step 5.2: Update GoDaddy DNS (Manual)
```bash
# Add these records in GoDaddy DNS:
# Type: A
# Name: admin
# Value: [Backend IP from terraform output]

# Type: CNAME
# Name: www.admin  
# Value: [Amplify domain from terraform output]
```

### Step 5.3: Verify SSL Certificate
```bash
# SSL is automatically configured by:
# - Certbot on EC2 (backend)
# - Amplify (frontend)

# Test both:
curl -I https://admin.pgeers.nl/api/status
curl -I https://admin.pgeers.nl
```

**✅ Checkpoint**: Custom domain working with SSL

---

## Phase 7: Infrastructure Validation

### Step 6.1: Automated Testing
```bash
# infrastructure/test.sh
#!/bin/bash
set -e

BACKEND_IP=$(terraform output -raw instance_ip)
FRONTEND_URL=$(terraform output -raw amplify_url)

echo "Testing backend API..."
curl -f -u admin:password http://$BACKEND_IP/api/status

echo "Testing frontend..."
curl -f $FRONTEND_URL

echo "Testing SSL..."
curl -f -k https://admin.pgeers.nl/api/status

echo "All tests passed!"
```

### Step 6.2: Infrastructure State Management
```bash
# Store Terraform state in S3 (recommended)
# Add to main.tf:
terraform {
  backend "s3" {
    bucket = "myadmin-terraform-state"
    key    = "production/terraform.tfstate"
    region = "eu-central-1"
  }
}
```

**✅ Checkpoint**: HTTPS working for both frontend and backend

---

## Phase 8: Add Backend Control Features

### Step 7.1: Add Backend Control API Endpoints
```python
# Add to backend/src/app.py

@app.route('/api/backend/status', methods=['GET'])
def backend_status():
    """Check if backend services are running on EC2"""
    try:
        import subprocess
        import os
        
        # Check if we're running in production (EC2)
        if os.path.exists('/home/ec2-user'):
            # Check docker containers status
            result = subprocess.run(['docker', 'ps', '--format', 'table {{.Names}}\t{{.Status}}'], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                containers = result.stdout
                running = 'myadmin' in containers and 'Up' in containers
            else:
                running = False
        else:
            # Local development - always running
            running = True
        
        return jsonify({
            'success': True,
            'running': running
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/backend/start', methods=['POST'])
def backend_start():
    """Start backend services on EC2"""
    try:
        import subprocess
        import os
        
        # Check if we're running in production (EC2)
        if os.path.exists('/home/ec2-user'):
            # Start docker containers
            result = subprocess.run(['docker-compose', 'up', '-d'], 
                                  cwd='/home/ec2-user/myAdmin',
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                return jsonify({
                    'success': True,
                    'message': 'Backend services started successfully'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': f'Failed to start services: {result.stderr}'
                }), 500
        else:
            # Local development - simulate success
            return jsonify({
                'success': True,
                'message': 'Backend already running (development mode)'
            })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/backend/stop', methods=['POST'])
def backend_stop():
    """Stop backend services on EC2"""
    try:
        import subprocess
        import os
        
        # Check if we're running in production (EC2)
        if os.path.exists('/home/ec2-user'):
            # Stop docker containers
            result = subprocess.run(['docker-compose', 'down'], 
                                  cwd='/home/ec2-user/myAdmin',
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                return jsonify({
                    'success': True,
                    'message': 'Backend services stopped successfully'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': f'Failed to stop services: {result.stderr}'
                }), 500
        else:
            # Local development - simulate success
            return jsonify({
                'success': True,
                'message': 'Cannot stop in development mode'
            })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
```

### Step 7.2: Add Frontend Control Interface
```typescript
// Add to frontend/src/App.tsx

// Add state
const [backendStatus, setBackendStatus] = useState({ running: false, loading: false });

// Add functions
const checkBackendStatus = async () => {
  try {
    const response = await fetch('/api/backend/status');
    const data = await response.json();
    setBackendStatus({ running: data.running, loading: false });
  } catch (error) {
    setBackendStatus({ running: false, loading: false });
  }
};

const controlBackend = async (action: 'start' | 'stop') => {
  setBackendStatus(prev => ({ ...prev, loading: true }));
  try {
    const response = await fetch(`/api/backend/${action}`, { method: 'POST' });
    const data = await response.json();
    if (data.success) {
      setTimeout(checkBackendStatus, 2000); // Check status after 2 seconds
    }
  } catch (error) {
    console.error(`Error ${action}ing backend:`, error);
  } finally {
    setBackendStatus(prev => ({ ...prev, loading: false }));
  }
};

// Add to useEffect
useEffect(() => {
  // ... existing code ...
  checkBackendStatus();
}, []);

// Add to main menu JSX
<HStack spacing={2} w="full">
  <Button 
    size="sm" 
    colorScheme={backendStatus.running ? "red" : "green"}
    onClick={() => controlBackend(backendStatus.running ? 'stop' : 'start')}
    isLoading={backendStatus.loading}
    flex={1}
  >
    {backendStatus.running ? '⏹️ Stop Backend' : '▶️ Start Backend'}
  </Button>
  <Button 
    size="sm" 
    variant="outline" 
    onClick={checkBackendStatus}
    isLoading={backendStatus.loading}
  >
    🔄 Status
  </Button>
</HStack>
```

### Step 7.3: Update CORS for Production
```python
# Update CORS in backend/src/app.py
CORS(app, resources={
    r"/api/*": {
        "origins": ["http://localhost:3000", "https://admin.pgeers.nl"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})
```

**✅ Checkpoint**: Backend control buttons functional

---

## Phase 9: Final Testing & Validation

### Step 9.1: End-to-End Testing
```bash
# Test complete workflow:
1. Visit https://admin.pgeers.nl
2. Should show Basic Auth popup
3. Enter credentials
4. Test each function:
   - Import Invoices (upload PDF)
   - Check Invoice Exists
   - Import Banking Accounts
   - Import STR Bookings
   - STR Invoice Generator
   - STR Pricing Model
   - myAdmin Reports
```

### Step 9.2: API Impact Assessment
**Changes Made:**
- ✅ Frontend: Updated API URLs to use domain instead of localhost
- ✅ Backend: Updated CORS to allow domain origin
- ✅ Database: Changed host from localhost to container name
- ✅ Auth: Added Basic HTTP Auth to nginx

**No Changes Needed:**
- ✅ All API endpoints remain the same
- ✅ Request/response formats unchanged
- ✅ Database schema unchanged
- ✅ Business logic unchanged

### Step 9.3: Performance Testing
```bash
# Test API response times
curl -w "@curl-format.txt" -u admin:password https://admin.pgeers.nl/api/status

# Test file upload
curl -u admin:password -F "file=@test.pdf" https://admin.pgeers.nl/api/upload
```

### Step 9.4: Test Backend Control Features
```bash
# Test backend control from dashboard:
1. Visit https://admin.pgeers.nl
2. Check backend status shows correctly
3. Test Stop Backend button
4. Verify containers stop: ssh ec2-user@your-ip "docker ps"
5. Test Start Backend button
6. Verify containers start and application works
7. Test Status refresh button
```

**✅ Final Checkpoint**: Production system with backend control fully operational

---

## Rollback Plan (IaC)

```bash
# infrastructure/rollback.sh
#!/bin/bash

# Rollback to previous Terraform state
terraform workspace select production-backup
terraform apply

# Or destroy and recreate
terraform destroy -var="key_name=your-key-pair"
terraform apply -var="key_name=your-key-pair"

# Rollback Amplify deployment
aws amplify start-deployment --app-id $(terraform output -raw amplify_app_id) --branch-name main --job-id previous-job-id
```

## Infrastructure Management

```bash
# infrastructure/Makefile
.PHONY: plan apply destroy test

plan:
	terraform plan -var="key_name=$(KEY_NAME)"

apply:
	terraform apply -var="key_name=$(KEY_NAME)" -auto-approve

destroy:
	terraform destroy -var="key_name=$(KEY_NAME)" -auto-approve

test:
	./test.sh

deploy-app:
	ansible-playbook -i inventory.ini deploy.yml --ask-vault-pass

full-deploy: apply deploy-app test
```

## Cost Estimate
- **EC2 t3.small**: ~$15/month
- **Amplify**: ~$1/month (for your traffic)
- **Data transfer**: ~$1-2/month
- **Total**: ~$17-18/month

## Security Notes
- Basic Auth protects API endpoints
- SSL certificates for encryption
- EC2 security groups limit access
- MySQL only accessible from backend container