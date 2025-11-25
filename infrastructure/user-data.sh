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