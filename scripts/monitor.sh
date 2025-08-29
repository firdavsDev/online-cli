
#!/bin/bash
# monitor.sh - System monitoring and alerting script

set -e

WEBHOOK_URL="${WEBHOOK_URL:-""}"
ALERT_EMAIL="${ALERT_EMAIL:-""}"
LOG_FILE="/var/log/online-cli-monitor.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a $LOG_FILE
}

send_alert() {
    local message="$1"
    local severity="$2"
    
    log "ALERT [$severity]: $message"
    
    # Send to webhook if configured
    if [ -n "$WEBHOOK_URL" ]; then
        curl -s -X POST "$WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -d "{\"text\":\"🚨 Online CLI Alert [$severity]: $message\"}" || true
    fi
    
    # Send email if configured
    if [ -n "$ALERT_EMAIL" ] && command -v mail &> /dev/null; then
        echo "$message" | mail -s "Online CLI Alert [$severity]" "$ALERT_EMAIL" || true
    fi
}

check_docker_services() {
    log "Checking Docker services..."
    
    services=("postgres" "redis" "tunnel-server-1" "tunnel-server-2" "dashboard" "nginx")
    
    for service in "${services[@]}"; do
        if ! docker-compose ps $service | grep -q "Up"; then
            send_alert "Service $service is not running" "CRITICAL"
        fi
    done
}

check_disk_space() {
    log "Checking disk space..."
    
    usage=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ $usage -gt 85 ]; then
        send_alert "Disk usage is at ${usage}%" "WARNING"
    fi
    if [ $usage -gt 95 ]; then
        send_alert "Disk usage is critically high at ${usage}%" "CRITICAL"
    fi
}

check_memory_usage() {
    log "Checking memory usage..."
    
    mem_usage=$(free | grep Mem | awk '{printf "%.0f", ($3/$2)*100}')
    if [ $mem_usage -gt 90 ]; then
        send_alert "Memory usage is at ${mem_usage}%" "WARNING"
    fi
    if [ $mem_usage -gt 95 ]; then
        send_alert "Memory usage is critically high at ${mem_usage}%" "CRITICAL"
    fi
}

check_cpu_load() {
    log "Checking CPU load..."
    
    load1=$(uptime | awk '{print $10}' | sed 's/,//')
    cpu_count=$(nproc)
    load_threshold=$(echo "$cpu_count * 2" | bc)
    
    if (( $(echo "$load1 > $load_threshold" | bc -l) )); then
        send_alert "High CPU load: $load1 (threshold: $load_threshold)" "WARNING"
    fi
}

check_network_connectivity() {
    log "Checking network connectivity..."
    
    if ! ping -c 1 8.8.8.8 &> /dev/null; then
        send_alert "Network connectivity issue detected" "CRITICAL"
    fi
}

check_ssl_expiry() {
    log "Checking SSL certificate expiry..."
    
    if [ -f /etc/nginx/ssl/cert.pem ]; then
        expiry_date=$(openssl x509 -enddate -noout -in /etc/nginx/ssl/cert.pem | cut -d= -f2)
        expiry_epoch=$(date -d "$expiry_date" +%s)
        current_epoch=$(date +%s)
        days_until_expiry=$(( (expiry_epoch - current_epoch) / 86400 ))
        
        if [ $days_until_expiry -lt 30 ]; then
            send_alert "SSL certificate expires in $days_until_expiry days" "WARNING"
        fi
        if [ $days_until_expiry -lt 7 ]; then
            send_alert "SSL certificate expires in $days_until_expiry days" "CRITICAL"
        fi
    fi
}

check_log_errors() {
    log "Checking for errors in logs..."
    
    # Check for recent errors in application logs
    error_count=$(find /opt/online-cli/logs -name "*.log" -mmin -60 -exec grep -c "ERROR\|CRITICAL" {} \; 2>/dev/null | awk '{sum += $1} END {print sum}')
    
    if [ "$error_count" -gt 10 ]; then
        send_alert "High error rate detected: $error_count errors in the last hour" "WARNING"
    fi
}

generate_report() {
    log "Generating system report..."
    
    cat << EOF > /tmp/system_report.txt
Online CLI System Report - $(date)
=====================================

System Information:
- Uptime: $(uptime)
- Load: $(cat /proc/loadavg)
- Memory: $(free -h | grep Mem)
- Disk: $(df -h /)

Docker Services:
$(docker-compose ps)

Recent Logs (last 50 lines):
$(tail -50 /opt/online-cli/logs/server.log 2>/dev/null || echo "No server logs found")

EOF
    
    log "Report generated: /tmp/system_report.txt"
}

# Main monitoring loop
main() {
    case "${1:-check}" in
        "check")
            log "Starting monitoring checks..."
            check_docker_services
            check_disk_space
            check_memory_usage
            check_cpu_load
            check_network_connectivity
            check_ssl_expiry
            check_log_errors
            log "Monitoring checks completed"
            ;;
        "report")
            generate_report
            ;;
        "daemon")
            log "Starting monitoring daemon..."
            while true; do
                main check
                sleep 300  # Check every 5 minutes
            done
            ;;
        *)
            echo "Usage: $0 {check|report|daemon}"
            exit 1
            ;;
    esac
}

main "$@"