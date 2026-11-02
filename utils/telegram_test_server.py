import asyncio
from pathlib import Path

from loguru import logger
import typer
import random

from embykeeper.cli import AsyncTyper
from embykeeper.config import config
from embykeeper import var, __version__
from embykeeper.telegram.pyrogram import Client as PyroClient
from embykeeper.telegram.telethon import TelethonUtils
from embykeeper.telegram.session import API_ID, API_HASH, _test_dc_id, _test_dc_ip, _test_dc_port

app = AsyncTyper()


async def test_with_pyrogram(phone: str, dc_id: int):
    logger.info("[Pyrogram] Connecting to Telegram test server...")
    client = PyroClient(
        name="test_user_pyrogram",
        api_id=API_ID,
        api_hash=API_HASH,
        phone_number=phone,
        proxy=(config.proxy.model_dump() if config.proxy else None),
        workdir=Path(__file__).parent,
        in_memory=False,
        test_mode=True,
        app_version=__version__,
        device_model="A320MH",
        system_version="4.16.30-vxEmby",
        sleep_threshold=60,
        workers=4,
    )
    try:
        await client.connect()
        # Pre-fill the expected test code: dc_id repeated five times, e.g. 22222
        client.phone_code = str(dc_id) * 5
        user = await client.authorize()
        logger.success(f"[Pyrogram] Connected as {user.first_name} (id={user.id}).")
    finally:
        try:
            await client.stop()
        except Exception:
            pass


async def test_with_telethon(phone: str, dc_id: int):
    logger.info("[Telethon] Connecting to Telegram test server...")
    from telethon import TelegramClient

    telethon_proxy = None
    if config.proxy:
        telethon_proxy = {
            "proxy_type": config.proxy.scheme,
            "addr": config.proxy.hostname,
            "port": config.proxy.port,
        }
        if config.proxy.username:
            telethon_proxy["username"] = config.proxy.username
        if config.proxy.password:
            telethon_proxy["password"] = config.proxy.password

    client = TelegramClient(
        None,
        api_id=API_ID,
        api_hash=API_HASH,
        system_version="4.16.30-vxEMBY",
        device_model="A320MH",
        app_version=__version__,
        proxy=telethon_proxy,
    )

    # Switch to Telegram test DC. Use port 80 per official example.
    client.session.set_dc(dc_id, _test_dc_ip, 80)

    try:
        await TelethonUtils(client).start(
            phone=phone,
            password=lambda: "",
            code_callback=lambda: str(dc_id) * 5,
        )
        me = await client.get_me()
        logger.success(f"[Telethon] Connected as {getattr(me, 'first_name', 'Unknown')} (id={me.id}).")
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


@app.async_command()
async def main(
    config_file: Path = typer.Argument(None, dir_okay=False, allow_dash=True, envvar="EK_CONFIG_FILE"),
    lib: str = typer.Option("both", "--lib", "-l", help="telethon | pyrogram | both"),
    phone: str = typer.Option(None, "--phone", "-p", help="测试手机号, 自动生成如未提供"),
    dc: int = typer.Option(2, "--dc", help="测试服务器 DC 号 (1-3), 影响手机号与验证码"),
):
    var.debug = 2
    var.telegram_test_server = True
    await config.reload_conf(config_file)

    dc_id = int(dc)
    if dc_id not in (1, 2, 3):
        raise typer.BadParameter("--dc 仅支持 1, 2 或 3")

    # Auto-generate a test phone if not provided: 99966XYYYY
    if not phone:
        suffix = random.randint(0, 9999)
        phone = f"99966{dc_id}{suffix:04d}"
        logger.info(f"使用自动生成的测试手机号: {phone}")
    else:
        if not (phone.startswith("99966") and len(phone) >= 9):
            logger.warning("建议使用 Telegram 测试服务器专用手机号 (以 99966 开头).")

    lib = lib.lower().strip()
    if lib not in {"telethon", "pyrogram", "both"}:
        raise typer.BadParameter("--lib 仅支持 telethon | pyrogram | both")

    if lib in ("pyrogram", "both"):
        await test_with_pyrogram(phone, dc_id)
    if lib in ("telethon", "both"):
        await test_with_telethon(phone, dc_id)


if __name__ == "__main__":
    app()
