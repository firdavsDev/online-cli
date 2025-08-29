import asyncio
import base64
import json
import logging
import socket
import uuid

from aiohttp import WSMsgType, web

LOG = logging.getLogger("online-server")
logging.basicConfig(level=logging.INFO)

WS_PORT = 8765
PUBLIC_PORT_START = 5000
PUBLIC_PORT_END = 5999
REQUEST_TIMEOUT = 30  # seconds

# Global stores
clients = {}  # client_id -> {ws, runner, public_port, local_port}
port_map = {}  # public_port -> client_id
pending = {}  # request_id -> Future


def port_is_free(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", port))
        s.close()
        return True
    except OSError:
        return False


async def assign_public_port_for_client(ws, client_id, local_port):
    for p in range(PUBLIC_PORT_START, PUBLIC_PORT_END + 1):
        if p in port_map:
            continue
        if not port_is_free(p):
            continue

        # create aiohttp app that will forward incoming HTTP to the ws
        app = web.Application()

        async def proxy_handler(request):
            rid = str(uuid.uuid4())
            body = await request.read()
            msg = {
                "type": "request",
                "request_id": rid,
                "method": request.method,
                "path": str(request.rel_url),
                "headers": dict(request.headers),
                "body": base64.b64encode(body).decode("ascii"),
            }
            fut = asyncio.get_event_loop().create_future()
            pending[rid] = fut
            await ws.send_str(json.dumps(msg))
            try:
                resp = await asyncio.wait_for(fut, timeout=REQUEST_TIMEOUT)
            except asyncio.TimeoutError:
                pending.pop(rid, None)
                return web.Response(status=504, text="Gateway Timeout")
            # build response
            resp_body = (
                base64.b64decode(resp.get("body", "").encode())
                if resp.get("body")
                else b""
            )
            headers = resp.get("headers", {})
            status = resp.get("status", 200)
            # ❌ transport level headerlarni olib tashlaymiz
            for h in [
                "Transfer-Encoding",
                "Content-Length",
                "Content-Encoding",
                "Connection",
            ]:
                headers.pop(h, None)
            return web.Response(body=resp_body, status=status, headers=headers)

        app.router.add_route("*", "/{tail:.*}", proxy_handler)
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
        }
        port_map[p] = client_id
        LOG.info(
            "Assigned public port %d to client %s (local %s)", p, client_id, local_port
        )
        return p

    raise web.HTTPServiceUnavailable(text="No free public ports")


async def cleanup_client(client_id):
    info = clients.pop(client_id, None)
    if not info:
        return
    p = info.get("public_port")
    if p and p in port_map:
        port_map.pop(p, None)
    try:
        await info["runner"].cleanup()
    except Exception:
        LOG.exception("Error cleaning runner for %s", client_id)
    LOG.info("Cleaned client %s and freed port %s", client_id, p)


async def ws_handler(request):
    ws = web.WebSocketResponse(max_msg_size=20 * 1024 * 1024)  # 20 MB limit
    await ws.prepare(request)
    client_id = str(uuid.uuid4())
    LOG.info("WS connected: %s", client_id)

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except Exception:
                    LOG.warning("Invalid JSON from %s", client_id)
                    continue

                t = data.get("type")
                if t == "register":
                    local_port = data.get("local_port")
                    public_port = await assign_public_port_for_client(
                        ws, client_id, local_port
                    )
                    await ws.send_str(
                        json.dumps({"type": "registered", "public_port": public_port})
                    )
                elif t == "response":
                    rid = data.get("request_id")
                    fut = pending.pop(rid, None)
                    if fut and not fut.done():
                        fut.set_result(data)
                else:
                    LOG.warning("Unknown message type %s from %s", t, client_id)

            elif msg.type == WSMsgType.ERROR:
                LOG.error("WS error %s: %s", client_id, ws.exception())
    finally:
        LOG.info("WS disconnected: %s", client_id)
        await cleanup_client(client_id)
    return ws


app = web.Application()
app.add_routes([web.get("/ws", ws_handler)])

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=WS_PORT)
