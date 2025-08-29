# Online CLI - Production-Ready Ngrok Alternative

A powerful, self-hosted tunneling solution with enterprise-grade features including load balancing, monitoring, analytics, and high availability.

## 🚀 Features

### 📁 Folder Structure
```bash
online-cli/
├── server.py                 # Enhanced tunnel server
├── dashboard.py              # Web dashboard
├── client.py                 # Enhanced client
├── docker-compose.yml        # Service orchestration
├── docker/                   # Container definitions
│   ├── Dockerfile            # Base Dockerfile
│   ├── Dockerfile.nginx      # Nginx Dockerfile
│   └── Dockerfile.server     # Server Dockerfile
├── nginx/
│   ├── nginx.conf           # Main nginx config
│   └── conf.d/              # Site configurations
├── monitoring/
│   ├── prometheus.yml       # Metrics config
│   └── grafana/             # Dashboard configs
├── scripts/
│   ├── deploy.sh            # Deployment automation
│   ├── setup.sh             # Server initialization
│   ├── monitor.sh           # System monitoring
│   └── maintenance.sh       # Maintenance mode
├── scripts/init.sql         # Database schema
└── .env.example             # Environment variables
```

### Core Features
- **Secure HTTP/HTTPS Tunneling** - Expose local services to the internet securely
- **WebSocket Support** - Real-time bidirectional communication
- **Load Balancing** - Multiple server instances with intelligent request distribution
- **Auto-reconnection** - Robust client with automatic reconnection and retry logic
- **Custom Subdomains** - User-defined subdomain support

### Enterprise Features
- **Authentication & Authorization** - JWT-based auth with API keys
- **Analytics Dashboard** - Real-time statistics and historical data
- **Rate Limiting** - Per-IP and per-user rate limiting
- **SSL/TLS Termination** - Automatic HTTPS with Let's Encrypt
- **Database Storage** - PostgreSQL for persistence and analytics
- **Redis Caching** - Session management and caching layer

### Monitoring & Operations
- **Prometheus Metrics** - Comprehensive metrics collection
- **Grafana Dashboards** - Beautiful visualizations and alerts
- **Health Checks** - Automated health monitoring
- **Log Aggregation** - Centralized logging with rotation
- **Backup System** - Automated database and configuration backups

### Security Features
- **Nginx Reverse Proxy** - Advanced security and performance
- **Fail2ban Integration** - Automated intrusion prevention
- **Firewall Configuration** - UFW-based security rules
- **SSL/TLS Encryption** - End-to-end encryption
- **Security Headers** - OWASP recommended headers

## 📋 Prerequisites

- **Operating System**: Ubuntu 20.04+ / CentOS 8+ / Debian 11+
- **RAM**: Minimum 4GB (8GB recommended)
- **CPU**: 2+ cores recommended
- **Storage**: 50GB+ available space
- **Network**: Public IP address and domain name
- **Software**: Docker and Docker Compose

## 🛠 Installation

### 1. Initial Server Setup

```bash
# Clone the repository
git clone https://github.com/your-org/online-cli.git
cd online-cli

# Make scripts executable
chmod +x scripts/*.sh

# Run initial server setup (as root)
sudo ./scripts/setup.sh
```

### 2. Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit configuration (update all passwords and secrets!)
nano .env
```

**Important**: Update the following in `.env`:
- `DB_PASSWORD` - Strong database password
- `JWT_SECRET` - Random 64-character string
- `GRAFANA_PASSWORD` - Grafana admin password
- `DOMAIN` - Your domain name
- `SSL_EMAIL` - Email for Let's Encrypt

### 3. DNS Configuration

Set up DNS records for your domain:

```
A    your-domain.com        → Your server IP
A    *.your-domain.com      → Your server IP
CNAME api.your-domain.com   → your-domain.com
CNAME grafana.your-domain.com → your-domain.com
```

### 4. Deploy Services

```bash
# Build and deploy all services
./scripts/deploy.sh full

# Or step by step:
./scripts/deploy.sh build
./scripts/deploy.sh push
./scripts/deploy.sh deploy
```

### 5. SSL Certificate Setup

```bash
# Get SSL certificates (after deployment)
sudo certbot --nginx -d your-domain.com -d *.your-domain.com

# Or use the automated script
sudo ./scripts/ssl-renew.sh your-domain.com admin@your-domain.com
```

### 6. Verify Installation

```bash
# Check service health
./scripts/deploy.sh health

# View logs
docker-compose logs -f

# Access dashboard
curl https://your-domain.com/health
```

## 🔧 Usage

### Server Administration

```bash
# View service status
docker-compose ps

# Scale tunnel servers
docker-compose up -d --scale tunnel-server-1=2 --scale tunnel-server-2=2

# View real-time logs
docker-compose logs -f tunnel-server-1

# Backup data
./scripts/backup.sh

# Enable maintenance mode
./scripts/maintenance.sh on

# Disable maintenance mode
./scripts/maintenance.sh off
```

### Client Usage

#### Installation

```bash
# Install from source
pip install -e .

# Or install from package
pip install online-cli
```

#### Basic Usage

```bash
# Expose local port 3000
online tunnel 3000

# Use custom subdomain
online tunnel 3000 --subdomain myapp

# Configure server
online config wss://your-domain.com:8080/ws --api-key your-api-key

# Show status
online status
```

#### Advanced Usage

```bash
# Live status monitoring
online tunnel 3000 --live

# Custom configuration
online tunnel 8080 --server wss://custom-server.com:8080/ws --subdomain api

# Multiple tunnels (different terminals)
online tunnel 3000 --subdomain frontend &
online tunnel 5000 --subdomain backend &
online tunnel 8080 --subdomain api &
```

### Dashboard Access

- **Main Dashboard**: https://your-domain.com
- **Grafana Monitoring**: https://grafana.your-domain.com:3001
- **Prometheus Metrics**: https://your-domain.com:9090

Default credentials:
- Dashboard: Register new account or use admin/admin123
- Grafana: admin / (password from .env file)

## 🔍 Monitoring

### Metrics Available

- **Tunnel Metrics**: Active connections, request rates, response times
- **System Metrics**: CPU, memory, disk usage, network I/O
- **Application Metrics**: Error rates, authentication failures, API usage
- **Business Metrics**: User registrations, tunnel usage, feature adoption

### Alerts Configuration

Edit `monitoring/alert_rules.yml` to customize alerts:

```yaml
- alert: HighTunnelErrorRate
  expr: rate(tunnel_requests_failed_total[5m]) > 0.1
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "High error rate detected"
```

### Log Analysis

```bash
# View application logs
docker-compose logs tunnel-server-1 | grep ERROR

# Monitor access logs
tail -f /opt/online-cli/logs/nginx/access.log

# Search for specific patterns
grep "429" /opt/online-cli/logs/nginx/access.log | tail -20
```

## 🔐 Security

### Network Security

- All traffic encrypted with TLS 1.2+
- Nginx reverse proxy with security headers
- Rate limiting and DDoS protection
- Fail2ban for intrusion prevention
- UFW firewall with minimal open ports

### Application Security

- JWT-based authentication
- API key authorization
- CORS protection
- Input validation and sanitization
- SQL injection protection (parameterized queries)
- XSS protection headers

### Data Security

- Database encryption at rest
- Redis password protection
- Secure session management
- Regular security updates
- Audit logging

## 🚨 Troubleshooting

### Common Issues

#### Services Won't Start

```bash
# Check service logs
docker-compose logs service-name

# Verify configuration
docker-compose config

# Check system resources
df -h
free -m
```

#### Client Connection Issues

```bash
# Test WebSocket connectivity
curl -H "Connection: Upgrade" -H "Upgrade: websocket" \
     https://your-domain.com:8080/ws

# Check firewall
sudo ufw status

# Verify DNS
nslookup your-domain.com
```

#### Database Connection Problems

```bash
# Check PostgreSQL logs
docker-compose logs postgres

# Test connection
docker-compose exec postgres psql -U online_user -d online_cli

# Check connection pool
docker-compose exec dashboard python -c "
import asyncio
import asyncpg
asyncio.run(asyncpg.connect('postgresql://online_user:password@postgres:5432/online_cli'))
"
```

#### Performance Issues

```bash
# Monitor resource usage
docker stats

# Check system metrics
htop
iotop
nethogs

# Review slow queries
docker-compose exec postgres psql -U online_user -d online_cli \
  -c "SELECT * FROM pg_stat_activity WHERE state = 'active';"
```

### Debug Mode

Enable debug logging by setting environment variables:

```bash
# In docker-compose.yml
environment:
  - LOG_LEVEL=DEBUG
  - ASYNCIO_DEBUG=1
```

## 📊 Performance Optimization

### Scaling Guidelines

- **1-100 concurrent tunnels**: Single server setup
- **100-500 concurrent tunnels**: 2 tunnel servers + load balancing  
- **500+ concurrent tunnels**: Multiple servers + Redis cluster + DB optimization

### Optimization Tips

```bash
# Increase file descriptors
echo "* soft nofile 65536" >> /etc/security/limits.conf
echo "* hard nofile 65536" >> /etc/security/limits.conf

# Optimize PostgreSQL
# Edit postgresql.conf:
# shared_buffers = 256MB
# effective_cache_size = 1GB
# work_mem = 4MB

# Optimize Nginx
# Edit nginx.conf:
# worker_processes auto;
# worker_connections 4096;
# keepalive_timeout 65;
```

## 🔄 Backup & Recovery

### Automated Backups

```bash
# Backup script runs daily at 2 AM
cat /etc/cron.d/online-cli
```

### Manual Backup

```bash
# Full system backup
./scripts/backup.sh full

# Database only
docker-compose exec postgres pg_dump -U online_user online_cli > backup.sql

# Configuration backup
tar -czf config-backup.tar.gz .env nginx/ monitoring/
```

### Disaster Recovery

```bash
# Restore from backup
./scripts/restore.sh backup-20240101.tar.gz

# Database restore
docker-compose exec -T postgres psql -U online_user -d online_cli < backup.sql

# Configuration restore
tar -xzf config-backup.tar.gz
docker-compose up -d
```

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

### Development Setup

```bash
# Clone repository
git clone https://github.com/your-org/online-cli.git
cd online-cli

# Setup development environment
python -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt

# Run tests
pytest tests/

# Run linting
black .
flake8 .
mypy .
```

### Code Style

- Follow PEP 8 for Python code
- Use Black for code formatting
- Add type hints for all functions
- Write comprehensive docstrings
- Include unit tests for new features

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Inspired by [ngrok](https://ngrok.com/)
- Built with [aiohttp](https://github.com/aio-libs/aiohttp)
- UI components from [Rich](https://github.com/Textualize/rich)
- Monitoring with [Prometheus](https://prometheus.io/) & [Grafana](https://grafana.com/)

## 📞 Support

- **Documentation**: [https://docs.online-cli.com](https://docs.online-cli.com)
- **Issues**: [GitHub Issues](https://github.com/your-org/online-cli/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/online-cli/discussions)
- **Email**: support@online-cli.com

## 🗺 Roadmap

### Version 2.1 (Q2 2024)
- [ ] TCP tunnel support
- [ ] Custom domains with SSL
- [ ] Advanced analytics dashboard
- [ ] Multi-tenant architecture

### Version 2.2 (Q3 2024)
- [ ] Kubernetes deployment support
- [ ] OAuth2 integration
- [ ] Webhook notifications
- [ ] Traffic replay and debugging

### Version 3.0 (Q4 2024)
- [ ] Edge locations for global performance
- [ ] WebRTC P2P tunneling
- [ ] Mobile app for management
- [ ] Enterprise SSO integration

---

## 🔧 API Reference

### REST API Endpoints

#### Authentication

```bash
# Login
POST /api/login
{
  "username": "user@example.com",
  "password": "password"
}

# Register
POST /api/register
{
  "username": "newuser",
  "email": "user@example.com", 
  "password": "securepassword"
}
```

#### Tunnel Management

```bash
# List tunnels
GET /api/tunnels
Authorization: Bearer <jwt_token>

# Create tunnel
POST /api/tunnels
Authorization: Bearer <jwt_token>
{
  "local_port": 3000,
  "subdomain": "myapp",
  "protocol": "http"
}

# Delete tunnel
DELETE /api/tunnels/{tunnel_id}
Authorization: Bearer <jwt_token>
```

#### Analytics

```bash
# Get tunnel statistics
GET /api/analytics?days=7
Authorization: Bearer <jwt_token>

# Get real-time metrics
GET /api/metrics
Authorization: Bearer <jwt_token>
```

### WebSocket API

#### Connection

```javascript
// Connect to tunnel server
const ws = new WebSocket('wss://your-domain.com:8080/ws');

// Authentication
ws.send(JSON.stringify({
  type: 'auth',
  token: 'jwt_token_here'
}));
```

#### Messages

```javascript
// Register tunnel
{
  "type": "register",
  "local_port": 3000,
  "subdomain": "myapp"
}

// Response
{
  "type": "registered", 
  "public_port": 5001,
  "server_id": "server-1"
}

// Request forwarding
{
  "type": "request",
  "request_id": "uuid",
  "method": "GET",
  "path": "/api/users",
  "headers": {...},
  "body": "base64_encoded_data"
}

// Response
{
  "type": "response",
  "request_id": "uuid", 
  "status": 200,
  "headers": {...},
  "body": "base64_encoded_data"
}
```

## 🐳 Docker Reference

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_HOST` | PostgreSQL host | `postgres` |
| `DB_PASSWORD` | Database password | `secure_password` |
| `REDIS_HOST` | Redis host | `redis` |
| `JWT_SECRET` | JWT signing key | `change_this` |
| `WS_PORT` | WebSocket port | `8765` |
| `PUBLIC_PORT_START` | Port range start | `5000` |
| `PUBLIC_PORT_END` | Port range end | `5999` |
| `MAX_CLIENTS_PER_SERVER` | Client limit | `100` |
| `REQUEST_TIMEOUT` | Request timeout (s) | `30` |

### Health Check Endpoints

| Service | Endpoint | Description |
|---------|----------|-------------|
| Tunnel Server | `/health` | Service health status |
| Dashboard | `/health` | API health status |
| Nginx | `/nginx_status` | Nginx statistics |
| Postgres | SQL query | Database connectivity |
| Redis | `PING` command | Redis connectivity |

### Volume Mounts

```yaml
volumes:
  - ./logs:/app/logs                    # Application logs
  - ./nginx/conf.d:/etc/nginx/conf.d    # Nginx configuration
  - ./monitoring:/app/monitoring        # Monitoring configs
  - postgres_data:/var/lib/postgresql/data  # Database data
  - redis_data:/data                    # Redis data
```

## 🔍 Monitoring Setup

### Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'online-cli'
    static_configs:
      - targets: ['tunnel-server-1:8765', 'tunnel-server-2:8766']
    metrics_path: /metrics
    scrape_interval: 5s

  - job_name: 'node-exporter'
    static_configs:
      - targets: ['host:9100']
```

### Grafana Dashboard

Import dashboard JSON from `monitoring/grafana/dashboards/online-cli.json`:

- **System Overview**: CPU, memory, disk, network
- **Application Metrics**: Request rates, response times, error rates  
- **Tunnel Statistics**: Active connections, data transfer, user activity
- **Business Metrics**: User growth, feature usage, revenue metrics

### Alerting Rules

```yaml
# alerts.yml
groups:
  - name: online-cli-alerts
    rules:
      - alert: ServiceDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.job }} is down"
          
      - alert: HighErrorRate  
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate: {{ $value }}"
```

## 🛡 Security Hardening

### SSL/TLS Configuration

```nginx
# Strong SSL configuration
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
ssl_prefer_server_ciphers off;
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 10m;

# HSTS
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";

# Certificate pinning  
add_header Public-Key-Pins 'pin-sha256="base64+primary=="; pin-sha256="base64+backup=="; max-age=5184000; includeSubDomains';
```

### Rate Limiting

```nginx
# Rate limiting zones
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=tunnel:50m rate=100r/s;

# Apply limits
location /api/ {
    limit_req zone=api burst=20 nodelay;
}

location /tunnel/ {
    limit_req zone=tunnel burst=200 nodelay;  
}
```

### Database Security

```sql
-- Create read-only user for monitoring
CREATE USER monitoring_user WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE online_cli TO monitoring_user;
GRANT USAGE ON SCHEMA public TO monitoring_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO monitoring_user;

-- Enable row-level security
ALTER TABLE tunnels ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_tunnels ON tunnels FOR ALL TO app_user USING (user_id = current_user_id());
```

### Container Security

```dockerfile
# Use non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser

# Read-only filesystem
--read-only --tmpfs /tmp --tmpfs /var/tmp

# Security options
--security-opt=no-new-privileges:true
--cap-drop=ALL
--cap-add=NET_BIND_SERVICE
```

---

*This documentation is continuously updated. For the latest information, visit our [documentation site](https://docs.online-cli.com).*