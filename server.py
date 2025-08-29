import asyncio
import base64
import json
import logging
import os
import socket
import time
import uuid
from datetime import datetime

import aioredis
import asyncpg
from aiohttp import WSMsgType, web
from aiohttp_cors import setup as cors_setup

# Environment variables
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "online_cli")
DB_USER = os.getenv("DB_USER", "online_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "secure_password")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
SERVER_ID = os.getenv("SERVER_ID", "server-1")
WS_PORT = int(os.getenv("WS_PORT", "8765"))
PUBLIC_PORT_START = int(os.getenv("PUBLIC_PORT_START", "5000"))
PUBLIC_PORT_END = int(os.getenv("PUBLIC_PORT_END", "5999"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
MAX_CLIENTS_PER_SERVER = int(os.getenv("MAX_CLIENTS_PER_SERVER", "100"))

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("/app/logs/server.log"), logging.StreamHandler()],
)
LOG = logging.getLogger("online-server")

# Global stores
clients = {}  # client_id -> {ws, runner, public_port, local_port, created_at}
port_map = {}  # public_port -> client_id
pending = {}  # request_id -> Future
db_pool = None
redis_pool = None


# Metrics
class Metrics:
    def __init__(self):
        self.active_connections = 0
        self.total_requests = 0
        self.failed_requests = 0
        self.avg_response_time = 0.0
        self.start_time = time.time()


metrics = Metrics()


async def init_db():
    """Initialize database connection pool"""
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            min_size=5,
            max_size=20,
        )
        LOG.info("Database pool created successfully")
    except Exception as e:
        LOG.error(f"Failed to create database pool: {e}")
        raise


async def init_redis():
    """Initialize Redis connection"""
    global redis_pool
    try:
        redis_pool = aioredis.ConnectionPool.from_url(
            f"redis://{REDIS_HOST}:{REDIS_PORT}", max_connections=20
        )
        LOG.info("Redis pool created successfully")
    except Exception as e:
        LOG.error(f"Failed to create Redis pool: {e}")
        raise


def port_is_free(port):
    """Check if port is available"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", port))
        s.close()
        return True
    except OSError:
        return False


async def log_connection(
    client_id: str, public_port: int, local_port: int, action: str
):
    """Log connection events to database"""
    if not db_pool:
        return

    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO connection_logs (client_id, server_id, public_port, local_port, action, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                client_id,
                SERVER_ID,
                public_port,
                local_port,
                action,
                datetime.utcnow(),
            )
    except Exception as e:
        LOG.error(f"Failed to log connection: {e}")


async def update_client_activity(client_id: str):
    """Update client last activity in Redis"""
    if not redis_pool:
        return

    try:
        redis = aioredis.Redis(connection_pool=redis_pool)
        await redis.setex(f"client:{client_id}:activity", 300, int(time.time()))
    except Exception as e:
        LOG.error(f"Failed to update client activity: {e}")


async def cleanup_inactive_clients():
    """Cleanup inactive clients periodically"""
    while True:
        try:
            current_time = time.time()
            inactive_clients = []

            for client_id, info in clients.items():
                if current_time - info.get("last_activity", 0) > 300:  # 5 minutes
                    inactive_clients.append(client_id)

            for client_id in inactive_clients:
                LOG.info(f"Cleaning up inactive client: {client_id}")
                await cleanup_client(client_id)

        except Exception as e:
            LOG.error(f"Error in cleanup task: {e}")

        await asyncio.sleep(60)  # Check every minute


async def assign_public_port_for_client(ws, client_id: str, local_port: int) -> int:
    """Assign a public port to client with enhanced error handling"""
    if len(clients) >= MAX_CLIENTS_PER_SERVER:
        raise web.HTTPServiceUnavailable(text="Server at capacity")

    for p in range(PUBLIC_PORT_START, PUBLIC_PORT_END + 1):
        if p in port_map:
            continue
        if not port_is_free(p):
            continue

        app = web.Application()

        async def proxy_handler(request):
            start_time = time.time()
            rid = str(uuid.uuid4())

            try:
                # Update metrics
                metrics.total_requests += 1

                # Rate limiting check
                client_ip = request.remote
                if await is_rate_limited(client_ip):
                    metrics.failed_requests += 1
                    return web.Response(status=429, text="Rate limit exceeded")

                body = await request.read()
                msg = {
                    "type": "request",
                    "request_id": rid,
                    "method": request.method,
                    "path": str(request.rel_url),
                    "headers": dict(request.headers),
                    "body": base64.b64encode(body).decode("ascii"),
                    "client_ip": client_ip,
                    "timestamp": time.time(),
                }

                fut = asyncio.get_event_loop().create_future()
                pending[rid] = fut

                await ws.send_str(json.dumps(msg))
                await update_client_activity(client_id)

                try:
                    resp = await asyncio.wait_for(fut, timeout=REQUEST_TIMEOUT)
                except asyncio.TimeoutError:
                    pending.pop(rid, None)
                    metrics.failed_requests += 1
                    return web.Response(status=504, text="Gateway Timeout")

                # Update response time
                response_time = time.time() - start_time
                metrics.avg_response_time = (
                    metrics.avg_response_time + response_time
                ) / 2

                # Build response
                resp_body = (
                    base64.b64decode(resp.get("body", "").encode())
                    if resp.get("body")
                    else b""
                )
                headers = resp.get("headers", {})
                status = resp.get("status", 200)

                # Remove transport-level headers
                for h in [
                    "Transfer-Encoding",
                    "Content-Length",
                    "Content-Encoding",
                    "Connection",
                ]:
                    headers.pop(h, None)

                return web.Response(body=resp_body, status=status, headers=headers)

            except Exception as e:
                LOG.exception(f"Error in proxy handler: {e}")
                metrics.failed_requests += 1
                return web.Response(status=502, text="Bad Gateway")
            finally:
                pending.pop(rid, None)

        app.router.add_route("*", "/{tail:.*}", proxy_handler)

        # Add CORS support
        cors = cors_setup(app)
        cors.add(app.router.add_route("*", "/{tail:.*}", proxy_handler))

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", p)
        await site.start()

        clients[client_id] = {
            "ws": ws,
            "runner": runner,
            "site": site,
            "public_port": p,
            "local_port": local_port,
            "created_at": time.time(),
            "last_activity": time.time(),
        }
        port_map[p] = client_id

        # Log to database
        await log_connection(client_id, p, local_port, "connected")

        LOG.info(f"Assigned public port {p} to client {client_id} (local {local_port})")
        return p

    raise web.HTTPServiceUnavailable(text="No free public ports")


async def cleanup_client(client_id: str):
    """Enhanced client cleanup with database logging"""
    info = clients.pop(client_id, None)
    if not info:
        return

    p = info.get("public_port")
    if p and p in port_map:
        port_map.pop(p, None)

    try:
        await info["runner"].cleanup()
    except Exception:
        LOG.exception(f"Error cleaning runner for {client_id}")

    # Log disconnection
    await log_connection(client_id, p or 0, info.get("local_port", 0), "disconnected")

    # Update metrics
    metrics.active_connections = len(clients)

    LOG.info(f"Cleaned client {client_id} and freed port {p}")


async def is_rate_limited(client_ip: str) -> bool:
    """Check if client is rate limited"""
    if not redis_pool:
        return False

    try:
        redis = aioredis.Redis(connection_pool=redis_pool)
        key = f"rate_limit:{client_ip}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)  # 1 minute window
        return count > 100  # 100 requests per minute
    except Exception:
        return False


async def health_check(request):
    """Health check endpoint"""
    return web.json_response(
        {
            "status": "healthy",
            "server_id": SERVER_ID,
            "active_connections": len(clients),
            "uptime": time.time() - metrics.start_time,
            "total_requests": metrics.total_requests,
            "failed_requests": metrics.failed_requests,
            "avg_response_time": metrics.avg_response_time,
        }
    )


async def metrics_endpoint(request):
    """Metrics endpoint for monitoring"""
    return web.json_response(
        {
            "server_id": SERVER_ID,
            "active_connections": len(clients),
            "total_requests": metrics.total_requests,
            "failed_requests": metrics.failed_requests,
            "avg_response_time": metrics.avg_response_time,
            "uptime": time.time() - metrics.start_time,
            "port_utilization": len(port_map)
            / (PUBLIC_PORT_END - PUBLIC_PORT_START + 1),
        }
    )


async def ws_handler(request):
    """Enhanced WebSocket handler"""
    ws = web.WebSocketResponse(max_msg_size=20 * 1024 * 1024)
    await ws.prepare(request)
    client_id = str(uuid.uuid4())

    LOG.info(f"WS connected: {client_id}")
    metrics.active_connections += 1

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except Exception:
                    LOG.warning(f"Invalid JSON from {client_id}")
                    continue

                t = data.get("type")
                if t == "register":
                    local_port = data.get("local_port")
                    if not local_port or not isinstance(local_port, int):
                        await ws.send_str(
                            json.dumps(
                                {"type": "error", "message": "Invalid local port"}
                            )
                        )
                        continue

                    try:
                        public_port = await assign_public_port_for_client(
                            ws, client_id, local_port
                        )
                        await ws.send_str(
                            json.dumps(
                                {
                                    "type": "registered",
                                    "public_port": public_port,
                                    "server_id": SERVER_ID,
                                }
                            )
                        )
                    except Exception as e:
                        await ws.send_str(
                            json.dumps({"type": "error", "message": str(e)})
                        )

                elif t == "response":
                    rid = data.get("request_id")
                    fut = pending.pop(rid, None)
                    if fut and not fut.done():
                        fut.set_result(data)

                elif t == "ping":
                    await ws.send_str(json.dumps({"type": "pong"}))
                    await update_client_activity(client_id)

                else:
                    LOG.warning(f"Unknown message type {t} from {client_id}")

            elif msg.type == WSMsgType.ERROR:
                LOG.error(f"WS error {client_id}: {ws.exception()}")

    except Exception as e:
        LOG.exception(f"Error in WS handler for {client_id}: {e}")
    finally:
        LOG.info(f"WS disconnected: {client_id}")
        await cleanup_client(client_id)
        metrics.active_connections = len(clients)

    return ws


async def init_app():
    """Initialize the application"""
    await init_db()
    await init_redis()

    app = web.Application()
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/health", health_check)
    app.router.add_get("/metrics", metrics_endpoint)

    # Start cleanup task
    asyncio.create_task(cleanup_inactive_clients())

    return app


if __name__ == "__main__":
    app = asyncio.get_event_loop().run_until_complete(init_app())
    web.run_app(app, host="0.0.0.0", port=WS_PORT)
