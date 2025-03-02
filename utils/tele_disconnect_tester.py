import asyncio
from pathlib import Path

from embykeeper.telegram.session import ClientsSession
from embykeeper.utils import AsyncTyper
from embykeeper.config import config

app = AsyncTyper()


@app.async_command()
async def main(config_file: Path):
    await config.reload_conf(config_file)
    print("Send 1")
    async with ClientsSession(config.telegram.account[:1]) as clients:
        async for _, tg in clients:
            await tg.send_message("me", "Test")
            break

    print("Wait for 300 seconds")
    await asyncio.sleep(300)

    async with ClientsSession(config.telegram.account[:1]) as clients:
        async for _, tg in clients:
            await tg.send_message("me", "Test")
            break
    print("Send 2")


if __name__ == "__main__":
    app()
