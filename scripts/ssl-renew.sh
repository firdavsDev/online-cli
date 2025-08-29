#!/bin/bash
# scripts/ssl-renew.sh - SSL certificate renewal script

DOMAIN=${1:-"your-domain.com"}
EMAIL=${2:-"admin@your-domain.com"}

echo "🔐 Renewing SSL certificates for $DOMAIN"

# Stop nginx temporarily
docker-compose stop nginx

# Renew certificates
certbot renew --standalone --preferred-challenges http

# Copy certificates to nginx directory
cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem /opt/online-cli/nginx/ssl/cert.pem
cp /etc/letsencrypt/live/$DOMAIN/privkey.pem /opt/online-cli/nginx/ssl/key.pem

# Set permissions
chmod 644 /opt/online-cli/nginx/ssl/cert.pem
chmod 600 /opt/online-cli/nginx/ssl/key.pem

# Restart nginx
docker-compose start nginx

echo "✅ SSL certificates renewed successfully"

# Add to cron for automatic renewal
echo "0 3 1 * * /opt/online-cli/scripts/ssl-renew.sh $DOMAIN $EMAIL" | crontab -
