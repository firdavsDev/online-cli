
#!/bin/bash
# setup.sh - Initial server setup script

set -e

log_info() {
    echo -e "\033[0;32m[INFO]\033[0m $1"
}

log_warn() {
    echo -e "\033[1;33m[WARN]\033[0m $1"
}

# Update system
update_system() {
    log_info "Updating system packages..."
    apt-get update && apt-get upgrade -y
    apt-get install -y curl wget git htop nano ufw fail2ban
}

# Install Docker
install_docker() {
    log_info "Installing Docker..."
    
    # Remove old versions
    apt-get remove -y docker docker-engine docker.io containerd runc || true
    
    # Install dependencies
    apt-get install -y \
        apt-transport-https \
        ca-certificates \
        curl \
        gnupg \
        lsb-release
    
    # Add Docker GPG key
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
    
    # Add Docker repository
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Install Docker
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    
    # Add user to docker group
    usermod -aG docker $USER
    
    # Start and enable Docker
    systemctl start docker
    systemctl enable docker
}

# Install Docker Compose
install_docker_compose() {
    log_info "Installing Docker Compose..."
    
    COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d\" -f4)
    curl -L "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    
    # Create symlink
    ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose
}

# Configure firewall
configure_firewall() {
    log_info "Configuring firewall..."
    
    # Reset UFW
    ufw --force reset
    
    # Default policies
    ufw default deny incoming
    ufw default allow outgoing
    
    # Allow SSH
    ufw allow ssh
    
    # Allow HTTP/HTTPS
    ufw allow 80/tcp
    ufw allow 443/tcp
    
    # Allow tunnel WebSocket
    ufw allow 8080/tcp
    
    # Allow tunnel ports range
    ufw allow 5000:5999/tcp
    
    # Allow monitoring (restrict to specific IPs in production)
    ufw allow 9090/tcp  # Prometheus
    ufw allow 3001/tcp  # Grafana
    
    # Enable firewall
    ufw --force enable
}

# Configure fail2ban
configure_fail2ban() {
    log_info "Configuring fail2ban..."
    
    cat > /etc/fail2ban/jail.local << EOF
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = ssh
logpath = /var/log/auth.log
maxretry = 3

[nginx-http-auth]
enabled = true
filter = nginx-http-auth
logpath = /var/log/nginx/error.log
maxretry = 3

[nginx-limit-req]
enabled = true
filter = nginx-limit-req
logpath = /var/log/nginx/error.log
maxretry = 10
EOF

    systemctl restart fail2ban
}

# Setup SSL certificates
setup_ssl() {
    log_info "Setting up SSL certificates..."
    
    # Install certbot
    apt-get install -y certbot python3-certbot-nginx
    
    log_warn "Run the following command after deployment to get SSL certificates:"
    log_warn "certbot --nginx -d your-domain.com -d *.your-domain.com"
}

# Create application directories
create_directories() {
    log_info "Creating application directories..."
    
    mkdir -p /opt/online-cli/{logs,data,backups}
    mkdir -p /opt/online-cli/nginx/{conf.d,ssl}
    mkdir -p /opt/online-cli/monitoring/{prometheus,grafana}
    
    # Set permissions
    chown -R 1000:1000 /opt/online-cli
}

# Setup monitoring
setup_monitoring() {
    log_info "Setting up monitoring..."
    
    # Install Node Exporter for system metrics
    NODE_EXPORTER_VERSION="1.6.1"
    cd /tmp
    wget https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz
    tar xzf node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz
    mv node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64/node_exporter /usr/local/bin/
    rm -rf node_exporter-${NODE_EXPORTER_VERSION}*
    
    # Create systemd service
    cat > /etc/systemd/system/node_exporter.service << EOF
[Unit]
Description=Node Exporter
After=network.target

[Service]
User=nobody
Group=nobody
Type=simple
ExecStart=/usr/local/bin/node_exporter

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl start node_exporter
    systemctl enable node_exporter
}

# Setup log rotation
setup_logrotate() {
    log_info "Setting up log rotation..."
    
    cat > /etc/logrotate.d/online-cli << EOF
/opt/online-cli/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 1000 1000
    postrotate
        docker-compose -f /opt/online-cli/docker-compose.yml restart nginx
    endscript
}
EOF
}

# Setup backup script
setup_backup() {
    log_info "Setting up backup script..."
    
    cat > /opt/online-cli/backup.sh << 'EOF'
#!/bin/bash

BACKUP_DIR="/opt/online-cli/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_BACKUP="$BACKUP_DIR/postgres_$DATE.sql"
REDIS_BACKUP="$BACKUP_DIR/redis_$DATE.rdb"

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup PostgreSQL
docker-compose exec -T postgres pg_dump -U online_user online_cli > $DB_BACKUP
gzip $DB_BACKUP

# Backup Redis
docker-compose exec -T redis redis-cli BGSAVE
sleep 5
docker cp $(docker-compose ps -q redis):/data/dump.rdb $REDIS_BACKUP
gzip $REDIS_BACKUP

# Keep only last 7 days of backups
find $BACKUP_DIR -name "*.gz" -mtime +7 -delete

echo "Backup completed: $DATE"
EOF

    chmod +x /opt/online-cli/backup.sh
    
    # Setup cron job for daily backups
    echo "0 2 * * * /opt/online-cli/backup.sh" | crontab -u root -
}

# Main setup
main() {
    log_info "Starting Online CLI server setup..."
    
    update_system
    install_docker
    install_docker_compose
    configure_firewall
    configure_fail2ban
    setup_ssl
    create_directories
    setup_monitoring
    setup_logrotate
    setup_backup
    
    log_info "Server setup completed! 🎉"
    log_warn "Please reboot the server and then run the deployment script."
    log_warn "Don't forget to:"
    log_warn "1. Update DNS records"
    log_warn "2. Get SSL certificates with certbot"
    log_warn "3. Update .env file with your configuration"
}

main "$@"