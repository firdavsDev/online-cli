import asyncio

import websockets  # pip

connections = {}
PORT = 8765  # WebSocket server porti


async def handler(websocket, path):
    # client "port=3000" deb yuboradi
    msg = await websocket.recv()
    client_port = msg.replace("port=", "")
    connections[client_port] = websocket
    print(f"[+] New tunnel registered: {client_port}")

    try:
        async for message in websocket:
            print(f"[Client {client_port}] {message}")
    except:
        print(f"[-] Client {client_port} disconnected")
        del connections[client_port]


async def main():
    async with websockets.serve(handler, "0.0.0.0", PORT):
        print(f"Server started at ws://0.0.0.0:{PORT}")
        await asyncio.Future()  # Run forever


asyncio.run(main())
