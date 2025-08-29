import asyncio
import json
import logging
import os
from datetime import datetime, timedelta

import aioredis
import asyncpg
import bcrypt
import jwt
from aiohttp import WSMsgType, web
from aiohttp_cors import setup as cors_setup
from cryptography.fernet import Fernet

# Environment variables
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "online_cli")
DB_USER = os.getenv("DB_USER", "online_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "secure_password")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
JWT_SECRET = os.getenv("JWT_SECRET", "your-jwt-secret")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "3000"))

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("dashboard")

# Global pools
db_pool = None
redis_pool = None
cipher_suite = Fernet(Fernet.generate_key())


class AuthMiddleware:
    def __init__(self):
        pass

    async def __call__(self, request, handler):
        # Skip auth for public endpoints
        if request.path in ["/api/login", "/api/register", "/health"]:
            return await handler(request)

        # Check JWT token
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return web.json_response({"error": "Authentication required"}, status=401)

        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            request["user_id"] = payload["user_id"]
            request["username"] = payload["username"]
            return await handler(request)
        except jwt.ExpiredSignatureError:
            return web.json_response({"error": "Token expired"}, status=401)
        except jwt.InvalidTokenError:
            return web.json_response({"error": "Invalid token"}, status=401)


async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        min_size=5,
        max_size=20,
    )


async def init_redis():
    global redis_pool
    redis_pool = aioredis.ConnectionPool.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}")


async def login_handler(request):
    """User login endpoint"""
    data = await request.json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return web.json_response(
            {"error": "Username and password required"}, status=400
        )

    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, username, password_hash, is_active FROM users WHERE username = $1",
            username,
        )

        if not user or not user["is_active"]:
            return web.json_response({"error": "Invalid credentials"}, status=401)

        if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
            return web.json_response({"error": "Invalid credentials"}, status=401)

        # Generate JWT token
        payload = {
            "user_id": str(user["id"]),
            "username": user["username"],
            "exp": datetime.utcnow() + timedelta(hours=24),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

        return web.json_response(
            {
                "token": token,
                "user": {"id": str(user["id"]), "username": user["username"]},
            }
        )


async def register_handler(request):
    """User registration endpoint"""
    data = await request.json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if not all([username, email, password]):
        return web.json_response({"error": "All fields required"}, status=400)

    # Hash password
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    try:
        async with db_pool.acquire() as conn:
            user_id = await conn.fetchval(
                """
                INSERT INTO users (username, email, password_hash) 
                VALUES ($1, $2, $3) 
                RETURNING id
                """,
                username,
                email,
                password_hash,
            )

            return web.json_response(
                {"message": "User registered successfully", "user_id": str(user_id)}
            )
    except asyncpg.UniqueViolationError:
        return web.json_response(
            {"error": "Username or email already exists"}, status=409
        )


async def dashboard_stats(request):
    """Get dashboard statistics"""
    user_id = request["user_id"]

    async with db_pool.acquire() as conn:
        # User's active tunnels
        tunnels = await conn.fetch(
            """
            SELECT t.*, 
                   COALESCE(rl.recent_requests, 0) as recent_requests
            FROM tunnels t
            LEFT JOIN (
                SELECT tunnel_id, COUNT(*) as recent_requests
                FROM request_logs
                WHERE created_at >= NOW() - INTERVAL '1 hour'
                GROUP BY tunnel_id
            ) rl ON t.id = rl.tunnel_id
            WHERE t.user_id = $1 AND t.status = 'active'
            ORDER BY t.created_at DESC
            """,
            user_id,
        )

        # Usage statistics
        stats = await conn.fetchrow(
            """
            SELECT 
                COUNT(*) FILTER (WHERE status = 'active') as active_tunnels,
                COUNT(*) as total_tunnels,
                COALESCE(SUM(bytes_transferred), 0) as total_bytes,
                COALESCE(SUM(requests_count), 0) as total_requests
            FROM tunnels 
            WHERE user_id = $1 AND created_at >= NOW() - INTERVAL '30 days'
            """,
            user_id,
        )

        # Recent activity
        recent_activity = await conn.fetch(
            """
            SELECT action, created_at, public_port, local_port
            FROM connection_logs cl
            JOIN tunnels t ON cl.client_id = t.client_id
            WHERE t.user_id = $1
            ORDER BY cl.created_at DESC
            LIMIT 10
            """,
            user_id,
        )

    return web.json_response(
        {
            "tunnels": [dict(t) for t in tunnels],
            "stats": dict(stats),
            "recent_activity": [dict(a) for a in recent_activity],
        },
        default=str,
    )


async def create_tunnel_handler(request):
    """Create new tunnel configuration"""
    data = await request.json()
    user_id = request["user_id"]

    local_port = data.get("local_port")
    subdomain = data.get("subdomain")

    if not local_port:
        return web.json_response({"error": "Local port required"}, status=400)

    try:
        async with db_pool.acquire() as conn:
            tunnel_id = await conn.fetchval(
                """
                INSERT INTO tunnels (user_id, local_port, subdomain, status)
                VALUES ($1, $2, $3, 'pending')
                RETURNING id
                """,
                user_id,
                local_port,
                subdomain,
            )

            return web.json_response(
                {"tunnel_id": str(tunnel_id), "message": "Tunnel configuration created"}
            )
    except Exception as e:
        LOG.error(f"Error creating tunnel: {e}")
        return web.json_response({"error": "Failed to create tunnel"}, status=500)


async def analytics_handler(request):
    """Get analytics data"""
    user_id = request["user_id"]
    days = int(request.query.get("days", 7))

    async with db_pool.acquire() as conn:
        # Request analytics
        request_stats = await conn.fetch(
            """
            SELECT 
                DATE(rl.created_at) as date,
                COUNT(*) as requests,
                COUNT(DISTINCT rl.ip_address) as unique_visitors,
                AVG(rl.response_time_ms) as avg_response_time
            FROM request_logs rl
            JOIN tunnels t ON rl.tunnel_id = t.id
            WHERE t.user_id = $1 AND rl.created_at >= NOW() - INTERVAL '%s days'
            GROUP BY DATE(rl.created_at)
            ORDER BY date DESC
            """,
            user_id,
            days,
        )

        # Status code distribution
        status_distribution = await conn.fetch(
            """
            SELECT 
                CASE 
                    WHEN status_code < 300 THEN '2xx'
                    WHEN status_code < 400 THEN '3xx'
                    WHEN status_code < 500 THEN '4xx'
                    ELSE '5xx'
                END as status_range,
                COUNT(*) as count
            FROM request_logs rl
            JOIN tunnels t ON rl.tunnel_id = t.id
            WHERE t.user_id = $1 AND rl.created_at >= NOW() - INTERVAL '%s days'
            GROUP BY status_range
            """,
            user_id,
            days,
        )

        # Top paths
        top_paths = await conn.fetch(
            """
            SELECT path, COUNT(*) as count
            FROM request_logs rl
            JOIN tunnels t ON rl.tunnel_id = t.id
            WHERE t.user_id = $1 AND rl.created_at >= NOW() - INTERVAL '%s days'
            GROUP BY path
            ORDER BY count DESC
            LIMIT 10
            """,
            user_id,
            days,
        )

    return web.json_response(
        {
            "request_stats": [dict(r) for r in request_stats],
            "status_distribution": [dict(s) for s in status_distribution],
            "top_paths": [dict(p) for p in top_paths],
        },
        default=str,
    )


async def websocket_handler(request):
    """WebSocket handler for real-time updates"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    # Authentication for WebSocket
    user_id = request.get("user_id")
    if not user_id:
        await ws.close(code=4001, message=b"Authentication required")
        return ws

    LOG.info(f"WebSocket connected for user {user_id}")

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                data = json.loads(msg.data)

                if data.get("type") == "subscribe_stats":
                    # Send periodic stats updates
                    asyncio.create_task(send_periodic_stats(ws, user_id))

            elif msg.type == WSMsgType.ERROR:
                LOG.error(f"WebSocket error: {ws.exception()}")

    except Exception as e:
        LOG.error(f"WebSocket handler error: {e}")
    finally:
        LOG.info(f"WebSocket disconnected for user {user_id}")

    return ws


async def send_periodic_stats(ws, user_id):
    """Send periodic statistics updates via WebSocket"""
    try:
        while not ws.closed:
            async with db_pool.acquire() as conn:
                stats = await conn.fetchrow(
                    """
                    SELECT 
                        COUNT(*) FILTER (WHERE status = 'active') as active_tunnels,
                        COALESCE(SUM(requests_count), 0) as total_requests
                    FROM tunnels 
                    WHERE user_id = $1
                    """,
                    user_id,
                )

                await ws.send_str(
                    json.dumps(
                        {"type": "stats_update", "data": dict(stats)}, default=str
                    )
                )

            await asyncio.sleep(5)  # Update every 5 seconds

    except Exception as e:
        LOG.error(f"Error sending periodic stats: {e}")


async def health_check(request):
    """Health check endpoint"""
    return web.json_response(
        {
            "status": "healthy",
            "service": "dashboard",
            "timestamp": datetime.utcnow().isoformat(),
        }
    )


async def server_status(request):
    """Get server status and metrics"""
    try:
        async with db_pool.acquire() as conn:
            server_metrics = await conn.fetch(
                """
                SELECT DISTINCT ON (server_id) 
                    server_id, active_connections, total_requests, 
                    failed_requests, avg_response_time, created_at
                FROM server_metrics 
                ORDER BY server_id, created_at DESC
                """
            )

            total_tunnels = await conn.fetchval(
                "SELECT COUNT(*) FROM tunnels WHERE status = 'active'"
            )

        return web.json_response(
            {
                "servers": [dict(s) for s in server_metrics],
                "total_active_tunnels": total_tunnels,
            },
            default=str,
        )

    except Exception as e:
        LOG.error(f"Error getting server status: {e}")
        return web.json_response({"error": "Failed to get server status"}, status=500)


# Static file serving
async def serve_static(request):
    """Serve static dashboard files"""
    path = request.match_info.get("path", "index.html")
    static_dir = "/app/static"

    if path == "":
        path = "index.html"

    file_path = os.path.join(static_dir, path)

    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        file_path = os.path.join(static_dir, "index.html")  # SPA fallback

    return web.FileResponse(file_path)


async def init_app():
    """Initialize the dashboard application"""
    await init_db()
    await init_redis()

    app = web.Application(middlewares=[AuthMiddleware()])

    # CORS setup
    cors = cors_setup(
        app,
        defaults={
            "*": {
                "allow_credentials": True,
                "allow_headers": ("Content-Type", "Authorization"),
                "allow_methods": "*",
            }
        },
    )

    # API routes
    app.router.add_post("/api/login", login_handler)
    app.router.add_post("/api/register", register_handler)
    app.router.add_get("/api/dashboard", dashboard_stats)
    app.router.add_post("/api/tunnels", create_tunnel_handler)
    app.router.add_get("/api/analytics", analytics_handler)
    app.router.add_get("/api/server-status", server_status)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/health", health_check)

    # Static files
    app.router.add_get("/{path:.*}", serve_static)

    # Add CORS to all routes
    for route in list(app.router.routes()):
        cors.add(route)

    return app


if __name__ == "__main__":
    app = asyncio.get_event_loop().run_until_complete(init_app())
    web.run_app(app, host="0.0.0.0", port=DASHBOARD_PORT)
