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
  default = "eu-west-1"
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
  ami           = "ami-0c02fb55956c7d316"  # Amazon Linux 2 (eu-west-1)
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