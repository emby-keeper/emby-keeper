import asyncio
from pathlib import Path

import tomli as tomllib
from loguru import logger

from embykeeper.telegram.session import ClientsSession
from embykeeper.telegram.link import Link
from embykeeper.utils import AsyncTyper
from embykeeper.telegram.notify import start_notifier
from embykeeper.config import config

app = AsyncTyper()


@app.async_command()
async def log(config_file: Path):
    await config.reload_conf(config_file)
    await start_notifier(config)
    logger.bind(log=True).info("Test logging.")


@app.async_command()
async def disconnect(config_file: Path):
    await config.reload_conf(config_file)
    ClientsSession.watch = asyncio.create_task(ClientsSession.watchdog(40))
    print("Sending Test1")
    async with ClientsSession(config.telegram.account[:1]) as clients:
        async for _, client in clients:
            await Link(client).send_msg("ERROR#Test1")
            break
    print("Wait for 40 seconds")
    await asyncio.sleep(40)
    print("Watchdog should be triggered")
    print("Wait for another 20 seconds")
    await asyncio.sleep(20)
    async with ClientsSession(config.telegram.account[:1]) as clients:
        async for _, client in clients:
            await Link(client).send_msg("ERROR#Test1")
            break
    print("Sent Test2")


if __name__ == "__main__":
    app()
