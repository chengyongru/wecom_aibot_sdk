"""
Basic usage example for WeCom AI Bot SDK
"""

import asyncio
import signal

from wecom_aibot_sdk import WSClient, generate_req_id


async def main():
    # 1. Create client instance
    client = WSClient({
        "bot_id": "your-bot-id",       # Get from WeCom admin console
        "secret": "your-bot-secret",   # Get from WeCom admin console
    })

    # 2. Register event handlers

    # Handle authentication success
    async def on_authenticated(frame):
        print("Authenticated successfully")

    client.on("authenticated", on_authenticated)

    # Handle text messages with streaming reply
    async def on_text_message(frame):
        content = frame.body.get("text", {}).get("content", "")
        print(f"Received text: {content}")

        stream_id = generate_req_id("stream")

        # Send streaming intermediate content
        await client.reply_stream(frame, stream_id, "Thinking...", finish=False)

        # Send final result
        await asyncio.sleep(1)
        await client.reply_stream(
            frame,
            stream_id,
            f'Hello! You said: "{content}"',
            finish=True,
        )

    client.on("message.text", on_text_message)

    # Handle enter chat event (send welcome message)
    async def on_enter_chat(frame):
        await client.reply_welcome(frame, {
            "msgtype": "text",
            "text": {"content": "Hello! I'm your AI assistant. How can I help you?"},
        })

    client.on("event.enter_chat", on_enter_chat)

    # Handle image messages
    async def on_image_message(frame):
        body = frame.body
        image = body.get("image", {})
        url = image.get("url", "")
        aeskey = image.get("aeskey", "")

        if url and aeskey:
            buffer, filename = await client.download_file(url, aeskey)
            print(f"Downloaded image: {filename}, size: {len(buffer)} bytes")

    client.on("message.image", on_image_message)

    # Handle file messages
    async def on_file_message(frame):
        body = frame.body
        file_info = body.get("file", {})
        url = file_info.get("url", "")
        aeskey = file_info.get("aeskey", "")

        if url and aeskey:
            print(f"Received file, downloading...")
            print(f"aeskey length: {len(aeskey)}")
            try:
                buffer, filename = await client.download_file(url, aeskey)
                print(f"Downloaded file: {filename}, size: {len(buffer)} bytes")
            except Exception as e:
                print(f"Error downloading file: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()

    client.on("message.file", on_file_message)

    # Handle errors
    async def on_error(frame):
        print(f"Error: {frame.body}")

    client.on("error", on_error)

    # 3. Connect
    print("Connecting...")
    await client.connect_async()

    # 4. Graceful shutdown
    loop = asyncio.get_event_loop()

    def signal_handler():
        print("\nShutting down...")
        asyncio.create_task(client.disconnect())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    # Keep running
    print("Client running. Press Ctrl+C to exit.")
    try:
        while client.is_connected:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
