-- init.sql - Database initialization script

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Users table for authentication
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    api_key VARCHAR(255) UNIQUE,
    is_active BOOLEAN DEFAULT true,
    is_premium BOOLEAN DEFAULT false,
    max_tunnels INTEGER DEFAULT 3,
    rate_limit_per_minute INTEGER DEFAULT 100,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tunnels table to track active tunnels
CREATE TABLE IF NOT EXISTS tunnels (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    client_id VARCHAR(255) NOT NULL,
    server_id VARCHAR(50) NOT NULL,
    public_port INTEGER NOT NULL,
    local_port INTEGER NOT NULL,
    subdomain VARCHAR(100),
    protocol VARCHAR(10) DEFAULT 'http',
    status VARCHAR(20) DEFAULT 'active',
    bytes_transferred BIGINT DEFAULT 0,
    requests_count BIGINT DEFAULT 0,
    last_activity TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE
);

-- Connection logs for analytics and monitoring
CREATE TABLE IF NOT EXISTS connection_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id VARCHAR(255) NOT NULL,
    server_id VARCHAR(50) NOT NULL,
    public_port INTEGER,
    local_port INTEGER,
    action VARCHAR(50) NOT NULL, -- connected, disconnected, error
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Request logs for analytics
CREATE TABLE IF NOT EXISTS request_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tunnel_id UUID REFERENCES tunnels(id) ON DELETE CASCADE,
    method VARCHAR(10) NOT NULL,
    path TEXT NOT NULL,
    status_code INTEGER,
    response_time_ms INTEGER,
    bytes_sent BIGINT DEFAULT 0,
    bytes_received BIGINT DEFAULT 0,
    ip_address INET,
    user_agent TEXT,
    referer TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Server health metrics
CREATE TABLE IF NOT EXISTS server_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    server_id VARCHAR(50) NOT NULL,
    cpu_usage DECIMAL(5,2),
    memory_usage DECIMAL(5,2),
    active_connections INTEGER DEFAULT 0,
    total_requests BIGINT DEFAULT 0,
    failed_requests BIGINT DEFAULT 0,
    avg_response_time DECIMAL(10,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- API keys for client authentication
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    key_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    permissions JSONB DEFAULT '{"tunnels": true, "analytics": false, "admin": false}',
    last_used TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Webhooks for notifications
CREATE TABLE IF NOT EXISTS webhooks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    events TEXT[] DEFAULT ARRAY['tunnel.connected', 'tunnel.disconnected'],
    secret_token VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Rate limiting tracking
CREATE TABLE IF NOT EXISTS rate_limits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    identifier VARCHAR(255) NOT NULL, -- IP address or API key
    endpoint VARCHAR(100) NOT NULL,
    requests_count INTEGER DEFAULT 1,
    window_start TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(identifier, endpoint, window_start)
);

-- Indexes for better performance
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

CREATE INDEX IF NOT EXISTS idx_tunnels_user_id ON tunnels(user_id);
CREATE INDEX IF NOT EXISTS idx_tunnels_client_id ON tunnels(client_id);
CREATE INDEX IF NOT EXISTS idx_tunnels_server_id ON tunnels(server_id);
CREATE INDEX IF NOT EXISTS idx_tunnels_public_port ON tunnels(public_port);
CREATE INDEX IF NOT EXISTS idx_tunnels_status ON tunnels(status);
CREATE INDEX IF NOT EXISTS idx_tunnels_created_at ON tunnels(created_at);

CREATE INDEX IF NOT EXISTS idx_connection_logs_client_id ON connection_logs(client_id);
CREATE INDEX IF NOT EXISTS idx_connection_logs_server_id ON connection_logs(server_id);
CREATE INDEX IF NOT EXISTS idx_connection_logs_created_at ON connection_logs(created_at);

CREATE INDEX IF NOT EXISTS idx_request_logs_tunnel_id ON request_logs(tunnel_id);
CREATE INDEX IF NOT EXISTS idx_request_logs_created_at ON request_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_request_logs_method ON request_logs(method);
CREATE INDEX IF NOT EXISTS idx_request_logs_status_code ON request_logs(status_code);

CREATE INDEX IF NOT EXISTS idx_server_metrics_server_id ON server_metrics(server_id);
CREATE INDEX IF NOT EXISTS idx_server_metrics_created_at ON server_metrics(created_at);

CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_is_active ON api_keys(is_active);

CREATE INDEX IF NOT EXISTS idx_rate_limits_identifier ON rate_limits(identifier);
CREATE INDEX IF NOT EXISTS idx_rate_limits_window_start ON rate_limits(window_start);

-- Triggers for updating timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to cleanup old logs
CREATE OR REPLACE FUNCTION cleanup_old_logs(days_to_keep INTEGER DEFAULT 30)
RETURNS INTEGER AS $
DECLARE
    deleted_count INTEGER;
BEGIN
    -- Clean connection logs
    DELETE FROM connection_logs 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * days_to_keep;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    -- Clean request logs
    DELETE FROM request_logs 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * days_to_keep;
    
    -- Clean server metrics
    DELETE FROM server_metrics 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * days_to_keep;
    
    -- Clean rate limits
    DELETE FROM rate_limits 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 hour';
    
    RETURN deleted_count;
END;
$ LANGUAGE plpgsql;

-- Views for analytics
CREATE OR REPLACE VIEW active_tunnels_summary AS
SELECT 
    server_id,
    COUNT(*) as active_count,
    AVG(requests_count) as avg_requests,
    SUM(bytes_transferred) as total_bytes
FROM tunnels 
WHERE status = 'active' 
GROUP BY server_id;

CREATE OR REPLACE VIEW daily_usage_stats AS
SELECT 
    DATE(created_at) as date,
    COUNT(*) as tunnel_count,
    COUNT(DISTINCT client_id) as unique_clients,
    AVG(EXTRACT(EPOCH FROM (COALESCE(expires_at, CURRENT_TIMESTAMP) - created_at))/3600) as avg_session_hours
FROM tunnels 
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;

-- Initial admin user (password: admin123)
INSERT INTO users (username, email, password_hash, is_premium, max_tunnels, rate_limit_per_minute) 
VALUES (
    'admin', 
    'admin@online-cli.com', 
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewKyNiRUY9H4oSm6', 
    true, 
    100, 
    1000
) ON CONFLICT (username) DO NOTHING;

-- Sample data for testing
INSERT INTO users (username, email, password_hash, api_key) 
VALUES (
    'testuser', 
    'test@example.com', 
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewKyNiRUY9H4oSm6',
    'test_api_key_12345'
) ON CONFLICT (username) DO NOTHING;
