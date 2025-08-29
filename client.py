import argparse
import asyncio
import base64
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import aiohttp
import yaml
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

# Rich console for beautiful output
console = Console()

# Configuration
CONFIG_DIR = Path.home() / ".online-cli"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(CONFIG_DIR / "client.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
LOG = logging.getLogger("online-client")


class Config:
    def __init__(self):
        self.server_url = "wss://your-server.com:8080/ws"
        self.api_key = None
        self.default_subdomain = None
        self.auto_reconnect = True
        self.reconnect_delay = 5
        self.max_reconnect_attempts = 10
        self.request_timeout = 30
        self.heartbeat_interval = 30

    def load(self):
        """Load configuration from file"""
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                data = yaml.safe_load(f)
                for key, value in data.items():
                    if hasattr(self, key):
                        setattr(self, key, value)

    def save(self):
        """Save configuration to file"""
        CONFIG_DIR.mkdir(exist_ok=True)
        data = {
            "server_url": self.server_url,
            "api_key": self.api_key,
            "default_subdomain": self.default_subdomain,
            "auto_reconnect": self.auto_reconnect,
            "reconnect_delay": self.reconnect_delay,
            "max_reconnect_attempts": self.max_reconnect_attempts,
            "request_timeout": self.request_timeout,
            "heartbeat_interval": self.heartbeat_interval,
        }
        with open(CONFIG_FILE, "w") as f:
            yaml.dump(data, f, default_flow_style=False)


class TunnelClient:
    def __init__(self, config: Config):
        self.config = config
        self.connected = False
        self.reconnect_attempts = 0
        self.public_port = None
        self.server_id = None
        self.stats = {
            "requests_handled": 0,
            "bytes_transferred": 0,
            "avg_response_time": 0,
            "uptime_start": time.time(),
            "last_request": None,
        }
        self.heartbeat_task = None

    async def handle_request(self, payload, ws, local_port):
        """Handle incoming request with enhanced error handling and metrics"""
        start_time = time.time()
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
            # Add client identification headers
            headers.update(
                {
                    "X-Online-CLI-Client": "true",
                    "X-Online-CLI-Version": "2.0",
                    "X-Request-ID": rid,
                }
            )

            timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as sess:
                async with sess.request(
                    method, local_url, headers=headers, data=body
                ) as r:
                    resp_body = await r.read()
                    resp_headers = dict(r.headers)
                    resp_status = r.status

            # Update statistics
            self.stats["requests_handled"] += 1
            self.stats["bytes_transferred"] += len(body) + len(resp_body)
            response_time = (time.time() - start_time) * 1000
            self.stats["avg_response_time"] = (
                (self.stats["avg_response_time"] + response_time) / 2
                if self.stats["avg_response_time"]
                else response_time
            )
            self.stats["last_request"] = time.time()

        except asyncio.TimeoutError:
            LOG.warning(f"Request {rid} timed out")
            resp_status = 504
            resp_headers = {"Content-Type": "text/plain"}
            resp_body = b"Gateway Timeout"
        except aiohttp.ClientConnectorError:
            LOG.error(f"Cannot connect to local server on port {local_port}")
            resp_status = 502
            resp_headers = {"Content-Type": "text/plain"}
            resp_body = b"Bad Gateway - Local server not reachable"
        except Exception as e:
            LOG.exception(f"Error forwarding request {rid}")
            resp_status = 502
            resp_headers = {"Content-Type": "text/plain"}
            resp_body = str(e).encode()

        # Send response back
        msg = {
            "type": "response",
            "request_id": rid,
            "status": resp_status,
            "headers": resp_headers,
            "body": base64.b64encode(resp_body).decode(),
            "response_time_ms": int((time.time() - start_time) * 1000),
        }

        try:
            await ws.send_str(json.dumps(msg))
        except Exception as e:
            LOG.error(f"Failed to send response for {rid}: {e}")

    async def heartbeat(self, ws):
        """Send periodic heartbeat to maintain connection"""
        while self.connected:
            try:
                await ws.send_str(
                    json.dumps({"type": "ping", "timestamp": time.time()})
                )
                await asyncio.sleep(self.config.heartbeat_interval)
            except Exception as e:
                LOG.error(f"Heartbeat failed: {e}")
                break

    async def connect(self, local_port: int, subdomain: Optional[str] = None):
        """Connect to tunnel server with retry logic"""
        while self.reconnect_attempts < self.config.max_reconnect_attempts:
            try:
                console.print(
                    f"[yellow]Connecting to {self.config.server_url}...[/yellow]"
                )

                headers = {}
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"

                session = aiohttp.ClientSession()
                async with session.ws_connect(
                    self.config.server_url,
                    max_msg_size=20 * 1024 * 1024,
                    headers=headers,
                ) as ws:
                    # Register tunnel
                    register_msg = {
                        "type": "register",
                        "local_port": local_port,
                        "subdomain": subdomain,
                        "client_version": "2.0",
                    }
                    await ws.send_str(json.dumps(register_msg))

                    # Start heartbeat
                    self.heartbeat_task = asyncio.create_task(self.heartbeat(ws))

                    # Process messages
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._handle_message(msg, ws, local_port)
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            console.print("[red]WebSocket closed by server[/red]")
                            break
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            console.print("[red]WebSocket error occurred[/red]")
                            break

                await session.close()

            except Exception as e:
                self.connected = False
                self.reconnect_attempts += 1

                if self.heartbeat_task:
                    self.heartbeat_task.cancel()

                console.print(f"[red]Connection failed: {e}[/red]")

                if self.reconnect_attempts < self.config.max_reconnect_attempts:
                    console.print(
                        f"[yellow]Retrying in {self.config.reconnect_delay} seconds... "
                        f"(Attempt {self.reconnect_attempts}/{self.config.max_reconnect_attempts})[/yellow]"
                    )
                    await asyncio.sleep(self.config.reconnect_delay)
                else:
                    console.print(
                        "[red]Max reconnection attempts reached. Giving up.[/red]"
                    )
                    return

        console.print("[red]Connection failed permanently[/red]")

    async def _handle_message(self, msg, ws, local_port):
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(msg.data)
            msg_type = data.get("type")

            if msg_type == "registered":
                self.connected = True
                self.reconnect_attempts = 0
                self.public_port = data.get("public_port")
                self.server_id = data.get("server_id")

                # Show success message
                panel = Panel.fit(
                    f"✅ Tunnel established!\n\n"
                    f"🌐 Public URL: [bold green]https://your-server.com:{self.public_port}[/bold green]\n"
                    f"🏠 Local URL: [bold blue]http://127.0.0.1:{local_port}[/bold blue]\n"
                    f"🖥️  Server: [dim]{self.server_id}[/dim]",
                    title="Online CLI Tunnel",
                    border_style="green",
                )
                console.print(panel)

            elif msg_type == "request":
                # Handle request asynchronously
                asyncio.create_task(self.handle_request(data, ws, local_port))

            elif msg_type == "pong":
                # Heartbeat response
                pass

            elif msg_type == "error":
                error_msg = data.get("message", "Unknown error")
                console.print(f"[red]Server error: {error_msg}[/red]")

            else:
                LOG.warning(f"Unknown message type: {msg_type}")

        except json.JSONDecodeError:
            LOG.warning("Received invalid JSON message")
        except Exception as e:
            LOG.error(f"Error handling message: {e}")

    def get_status_table(self):
        """Create status table for live display"""
        table = Table(title="Tunnel Status")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        uptime = int(time.time() - self.stats["uptime_start"])
        uptime_str = f"{uptime // 3600}h {(uptime % 3600) // 60}m {uptime % 60}s"

        table.add_row("Status", "🟢 Connected" if self.connected else "🔴 Disconnected")
        table.add_row(
            "Public Port", str(self.public_port) if self.public_port else "N/A"
        )
        table.add_row("Server ID", self.server_id or "N/A")
        table.add_row("Uptime", uptime_str)
        table.add_row("Requests Handled", str(self.stats["requests_handled"]))
        table.add_row("Bytes Transferred", f"{self.stats['bytes_transferred']:,} bytes")
        table.add_row("Avg Response Time", f"{self.stats['avg_response_time']:.2f} ms")

        if self.stats["last_request"]:
            last_req = int(time.time() - self.stats["last_request"])
            table.add_row("Last Request", f"{last_req}s ago")

        return table


def configure_server(url: str, api_key: Optional[str] = None):
    """Configure server settings"""
    config = Config()
    config.load()

    config.server_url = url
    if api_key:
        config.api_key = api_key

    config.save()
    console.print(f"[green]✅ Server configured: {url}[/green]")


def show_status():
    """Show current configuration and status"""
    config = Config()
    config.load()

    table = Table(title="Online CLI Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Server URL", config.server_url)
    table.add_row(
        "API Key", "***" + config.api_key[-4:] if config.api_key else "Not set"
    )
    table.add_row("Auto Reconnect", "✅" if config.auto_reconnect else "❌")
    table.add_row("Reconnect Delay", f"{config.reconnect_delay}s")
    table.add_row("Max Attempts", str(config.max_reconnect_attempts))
    table.add_row("Request Timeout", f"{config.request_timeout}s")
    table.add_row("Heartbeat Interval", f"{config.heartbeat_interval}s")

    console.print(table)


async def run_tunnel(
    local_port: int,
    server_ws_url: Optional[str] = None,
    subdomain: Optional[str] = None,
    live_status: bool = False,
):
    """Run the tunnel with optional live status display"""
    config = Config()
    config.load()

    if server_ws_url:
        config.server_url = server_ws_url

    client = TunnelClient(config)

    if live_status:
        with Live(client.get_status_table(), refresh_per_second=1) as live:

            async def update_display():
                while True:
                    live.update(client.get_status_table())
                    await asyncio.sleep(1)

            # Start display update task
            display_task = asyncio.create_task(update_display())

            try:
                await client.connect(local_port, subdomain)
            finally:
                display_task.cancel()
    else:
        await client.connect(local_port, subdomain)


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description="Online CLI - Ngrok Alternative")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Tunnel command (default)
    tunnel_parser = subparsers.add_parser("tunnel", help="Start tunnel")
    tunnel_parser.add_argument("port", type=int, help="Local port to expose")
    tunnel_parser.add_argument("--server", type=str, help="Server WebSocket URL")
    tunnel_parser.add_argument("--subdomain", type=str, help="Requested subdomain")
    tunnel_parser.add_argument("--live", action="store_true", help="Show live status")

    # Config command
    config_parser = subparsers.add_parser("config", help="Configure server")
    config_parser.add_argument("url", help="Server WebSocket URL")
    config_parser.add_argument("--api-key", type=str, help="API key for authentication")

    # Status command
    subparsers.add_parser("status", help="Show current configuration")

    args = parser.parse_args()

    try:
        if args.command == "config":
            configure_server(args.url, args.api_key)
        elif args.command == "status":
            show_status()
        elif args.command == "tunnel":
            asyncio.run(run_tunnel(args.port, args.server, args.subdomain, args.live))
        else:
            # Default to tunnel if no command specified
            if hasattr(args, "port"):
                asyncio.run(run_tunnel(args.port))
            else:
                parser.print_help()
    except KeyboardInterrupt:
        console.print("\n[yellow]Tunnel stopped by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
