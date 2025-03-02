from pathlib import Path

from embykeeper.telegram.session import ClientsSession
from embykeeper.utils import AsyncTyper
from embykeeper.config import config

app = AsyncTyper()


@app.async_command()
async def main(config_file: Path, url: str):
    await config.reload_conf(config_file)
    async with ClientsSession(config.telegram.account[:1]) as clients:
        async for _, tg in clients:
            try:
                # Parse message URL to get chat_id and message_id
                if not url.startswith("https://t.me/"):
                    print("Invalid Telegram message URL")
                    return

                parts = url.split("/")
                if len(parts) < 2:
                    print("Invalid URL format")
                    return

                chat_id = parts[-2]
                message_id = int(parts[-1])

                # Get message details
                message = await tg.get_messages(chat_id=chat_id, message_ids=message_id)
                if message:
                    print(message)
                else:
                    print("Message not found")
                break
            except Exception as e:
                print(f"Error: {e}")


if __name__ == "__main__":
    app()
