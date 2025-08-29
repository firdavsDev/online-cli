#!/bin/bash
# deploy.sh - Production deployment script

set -e

# Configuration
PROJECT_NAME="online-cli"
DOCKER_REGISTRY="your-registry.com"
VERSION=${1:-"latest"}
ENVIRONMENT=${2:-"production"}

echo "🚀 Deploying $PROJECT_NAME version $VERSION to $ENVIRONMENT environment..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    commands=("docker" "docker-compose" "git")
    for cmd in "${commands[@]}"; do
        if ! command -v $cmd &> /dev/null; then
            log_error "$cmd is not installed"
            exit 1
        fi
    done
    
    if ! docker info &> /dev/null; then
        log_error "Docker is not running"
        exit 1
    fi
    
    log_info "Prerequisites check passed ✅"
}

# Build images
build_images() {
    log_info "Building Docker images..."
    
    # Build server image
    docker build -f Dockerfile.server -t $DOCKER_REGISTRY/$PROJECT_NAME-server:$VERSION .
    
    # Build dashboard image
    docker build -f Dockerfile.dashboard -t $DOCKER_REGISTRY/$PROJECT_NAME-dashboard:$VERSION .
    
    # Build nginx image
    docker build -f Dockerfile.nginx -t $DOCKER_REGISTRY/$PROJECT_NAME-nginx:$VERSION .
    
    # Build client image
    docker build -f Dockerfile.client -t $DOCKER_REGISTRY/$PROJECT_NAME-client:$VERSION .
    
    log_info "Images built successfully ✅"
}

# Push images to registry
push_images() {
    log_info "Pushing images to registry..."
    
    docker push $DOCKER_REGISTRY/$PROJECT_NAME-server:$VERSION
    docker push $DOCKER_REGISTRY/$PROJECT_NAME-dashboard:$VERSION
    docker push $DOCKER_REGISTRY/$PROJECT_NAME-nginx:$VERSION
    docker push $DOCKER_REGISTRY/$PROJECT_NAME-client:$VERSION
    
    log_info "Images pushed successfully ✅"
}

# Deploy with Docker Compose
deploy() {
    log_info "Deploying services..."
    
    # Create environment file if it doesn't exist
    if [ ! -f .env ]; then
        log_warn "Creating .env file from template..."
        cp .env.example .env
        log_warn "Please update .env file with your configuration"
    fi
    
    # Pull latest images
    docker-compose pull
    
    # Deploy services
    docker-compose up -d --remove-orphans
    
    # Wait for services to be healthy
    log_info "Waiting for services to be healthy..."
    sleep 30
    
    # Check service health
    check_health
    
    log_info "Deployment completed successfully ✅"
}

# Health check
check_health() {
    log_info "Checking service health..."
    
    services=("postgres" "redis" "tunnel-server-1" "tunnel-server-2" "dashboard" "nginx")
    
    for service in "${services[@]}"; do
        if docker-compose ps $service | grep -q "Up (healthy)"; then
            log_info "$service is healthy ✅"
        else
            log_warn "$service is not healthy ⚠️"
            docker-compose logs --tail=20 $service
        fi
    done
}

# Rollback function
rollback() {
    log_warn "Rolling back to previous version..."
    
    # Get previous version from git
    PREV_VERSION=$(git describe --tags --abbrev=0 HEAD~1 2>/dev/null || echo "previous")
    
    if [ "$PREV_VERSION" != "previous" ]; then
        log_info "Rolling back to version $PREV_VERSION"
        # Update image tags and redeploy
        sed -i.bak "s/:$VERSION/:$PREV_VERSION/g" docker-compose.yml
        docker-compose up -d
        mv docker-compose.yml.bak docker-compose.yml
    else
        log_error "Cannot determine previous version for rollback"
        exit 1
    fi
}

# Cleanup old images and containers
cleanup() {
    log_info "Cleaning up old images and containers..."
    
    # Remove old images
    docker image prune -a -f --filter "until=72h"
    
    # Remove old containers
    docker container prune -f
    
    # Remove unused volumes
    docker volume prune -f
    
    # Remove unused networks
    docker network prune -f
    
    log_info "Cleanup completed ✅"
}

# Main deployment flow
main() {
    case "$1" in
        "build")
            check_prerequisites
            build_images
            ;;
        "push")
            push_images
            ;;
        "deploy")
            check_prerequisites
            deploy
            ;;
        "full")
            check_prerequisites
            build_images
            push_images
            deploy
            ;;
        "health")
            check_health
            ;;
        "rollback")
            rollback
            ;;
        "cleanup")
            cleanup
            ;;
        *)
            echo "Usage: $0 {build|push|deploy|full|health|rollback|cleanup}"
            echo ""
            echo "Commands:"
            echo "  build     - Build Docker images"
            echo "  push      - Push images to registry"
            echo "  deploy    - Deploy services"
            echo "  full      - Build, push, and deploy"
            echo "  health    - Check service health"
            echo "  rollback  - Rollback to previous version"
            echo "  cleanup   - Clean up old images and containers"
            exit 1
            ;;
    esac
}

# Run with parameters
if [ $# -eq 0 ]; then
    main "full"
else
    main "$@"
fi
