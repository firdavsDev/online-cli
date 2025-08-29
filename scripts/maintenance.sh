#!/bin/bash

MAINTENANCE_FILE="/tmp/maintenance.html"
NGINX_CONTAINER="online-cli-nginx-1"

enable_maintenance() {
    echo "🔧 Enabling maintenance mode..."
    
    cat > $MAINTENANCE_FILE << 'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Online CLI - Maintenance</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            margin: 0;
            padding: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            text-align: center;
            padding: 2rem;
            max-width: 600px;
        }
        .icon {
            font-size: 4rem;
            margin-bottom: 1rem;
        }
        h1 {
            font-size: 2.5rem;
            margin-bottom: 1rem;
        }
        p {
            font-size: 1.2rem;
            opacity: 0.9;
            line-height: 1.6;
        }
        .status {
            margin-top: 2rem;
            padding: 1rem;
            background: rgba(255,255,255,0.1);
            border-radius: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">🔧</div>
        <h1>Maintenance Mode</h1>
        <p>Online CLI is currently undergoing maintenance to improve your experience.</p>
        <p>We'll be back shortly. Thank you for your patience!</p>
        <div class="status">
            <p><strong>Status:</strong> Scheduled Maintenance</p>
            <p><strong>Started:</strong> <script>document.write(new Date().toLocaleString())</script></p>
        </div>
    </div>
</body>
</html>
EOF
    
    # Copy maintenance page to nginx container
    docker cp $MAINTENANCE_FILE $NGINX_CONTAINER:/usr/share/nginx/html/maintenance.html
    
    # Create maintenance configuration
    cat > /tmp/maintenance.conf << 'EOF'
server {
    listen 80 default_server;
    listen 443 ssl default_server;
    server_name _;
    
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    
    location / {
        root /usr/share/nginx/html;
        try_files /maintenance.html =503;
    }
    
    # Allow health checks
    location /health {
        return 200 "maintenance mode";
        add_header Content-Type text/plain;
    }
}
EOF
    
    docker cp /tmp/maintenance.conf $NGINX_CONTAINER:/etc/nginx/conf.d/maintenance.conf
    docker exec $NGINX_CONTAINER nginx -s reload
    
    echo "✅ Maintenance mode enabled"
}

disable_maintenance() {
    echo "🚀 Disabling maintenance mode..."
    
    docker exec $NGINX_CONTAINER rm -f /etc/nginx/conf.d/maintenance.conf
    docker exec $NGINX_CONTAINER nginx -s reload
    
    echo "✅ Maintenance mode disabled"
}

case "$1" in
    "on"|"enable")
        enable_maintenance
        ;;
    "off"|"disable")
        disable_maintenance
        ;;
    *)
        echo "Usage: $0 {on|off}"
        echo "  on/enable  - Enable maintenance mode"
        echo "  off/disable - Disable maintenance mode"
        exit 1
        ;;
esac
