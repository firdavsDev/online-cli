import argparse
import asyncio

import aiohttp
import websockets


async def forward(local_port):
    uri = "ws://0.0.0.0:8765"  # <-- bu yerga server IP yozing
    async with websockets.connect(uri) as websocket:
        await websocket.send(f"port={local_port}")
        print(f"Tunnel opened! Public URL: http://0.0.0.0:{local_port}")

        async for msg in websocket:
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(f"http://127.0.0.1:{local_port}") as resp:
                        text = await resp.text()
                        await websocket.send(text)
                except:
                    await websocket.send("Local server error")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True, help="Local port to expose")
    args = parser.parse_args()
    asyncio.run(forward(args.port))
