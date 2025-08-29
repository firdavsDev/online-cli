import argparse
import asyncio
import base64
import json
import logging
from urllib.parse import urlparse

import aiohttp

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("online-client")


async def handle_request(payload, ws, local_port):
    rid = payload["request_id"]
    method = payload["method"]
    path_qs = payload["path"]
    headers = payload.get("headers", {})
    body = (
        base64.b64decode(payload.get("body", "").encode())
        if payload.get("body")
        else b""
    )

    local_url = f"http://127.0.0.1:{local_port}{path_qs}"
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.request(method, local_url, headers=headers, data=body) as r:
                resp_body = await r.read()
                resp_headers = dict(r.headers)
                resp_status = r.status
    except Exception as e:
        LOG.exception("Error forwarding to local server")
        resp_status = 502
        resp_headers = {}
        resp_body = str(e).encode()

    msg = {
        "type": "response",
        "request_id": rid,
        "status": resp_status,
        "headers": resp_headers,
        "body": base64.b64encode(resp_body).decode(),
    }
    await ws.send_str(json.dumps(msg))


async def run(local_port, server_ws_url):
    parsed = urlparse(server_ws_url)
    host = parsed.hostname
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(
            server_ws_url, max_msg_size=20 * 1024 * 1024
        ) as ws:
            # register
            await ws.send_str(
                json.dumps({"type": "register", "local_port": local_port})
            )
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    t = data.get("type")
                    if t == "registered":
                        public_port = data.get("public_port")
                        print(f"✅ Tunnel opened: http://{host}:{public_port}")
                    elif t == "request":
                        # handle concurrently
                        asyncio.create_task(handle_request(data, ws, local_port))
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    print("WebSocket closed by server")
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    print("WebSocket error")
                    break


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port", type=int, required=True, help="Local port to expose (e.g. 3000)"
    )
    parser.add_argument(
        "--server",
        type=str,
        default="http://0.0.0.0:8765",
        help="Server WS URL (ws://server:8765/ws)",
    )
    args = parser.parse_args()
    server_ws_url = args.server
    if server_ws_url.startswith("http://"):
        server_ws_url = server_ws_url.replace("http://", "ws://")
    elif server_ws_url.startswith("https://"):
        server_ws_url = server_ws_url.replace("https://", "wss://")
    if not server_ws_url.endswith("/ws"):
        server_ws_url = server_ws_url.rstrip("/") + "/ws"
    asyncio.run(run(args.port, server_ws_url))


if __name__ == "__main__":
    main()
