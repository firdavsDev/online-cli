#!/bin/bash

SERVICE_NAME=${1:-"unknown"}
HEALTH_URL=${2:-"http://localhost/health"}
MAX_RETRIES=${3:-3}

echo "Health checking $SERVICE_NAME at $HEALTH_URL"

for i in $(seq 1 $MAX_RETRIES); do
    if curl -f -s --connect-timeout 5 --max-time 10 "$HEALTH_URL" > /dev/null 2>&1; then
        echo "$SERVICE_NAME is healthy"
        exit 0
    fi
    
    echo "Attempt $i/$MAX_RETRIES failed, retrying in 5 seconds..."
    sleep 5
done

echo "$SERVICE_NAME health check failed after $MAX_RETRIES attempts"
exit 1
