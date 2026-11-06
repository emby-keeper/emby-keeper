import asyncio
from datetime import datetime, timedelta
from io import BytesIO
import json
import multiprocessing
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import httpx
import psutil


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


async def verify_ocr():
    from PIL import Image, ImageDraw

    from embykeeper.ocr import OCRService

    image = Image.new("RGB", (160, 60), "white")
    ImageDraw.Draw(image).text((20, 20), "1234", fill="black")
    data = BytesIO()
    image.save(data, format="PNG")
    service = OCRService()
    try:
        result = await service.run(data)
        assert isinstance(result, str), result
    finally:
        await service.force_stop()


def verify_panel(directory):
    port, backend_port = free_port(), free_port()
    password = "portable-smoke-password"
    basedir = Path(directory)
    config = basedir / "config.toml"
    config.write_text("notifier = false\n", encoding="utf-8")
    env = {
        **os.environ,
        "HOME": directory,
        "USERPROFILE": directory,
        "EK_WEBPASS": password,
        "EMBYKEEPERAPI_BASEDIR": directory,
        "EMBYKEEPERAPI_CONFIG_FILE": str(config),
        "EMBYKEEPERAPI_SETTINGS_PATH": str(basedir / "settings.json"),
        "PYTHONIOENCODING": "utf-8",
    }
    for key in ("EK_CONFIG", "EK_MONGODB"):
        env.pop(key, None)
    started = time.monotonic()
    with (basedir / "panel.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "embykeeper",
                "web",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--target-port",
                str(backend_port),
            ],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=60, trust_env=False) as client:
                deadline = time.monotonic() + 60
                while True:
                    assert process.poll() is None, "Panel exited before becoming ready"
                    try:
                        client.get("/healthz").raise_for_status()
                        break
                    except httpx.HTTPError:
                        if time.monotonic() > deadline:
                            raise TimeoutError("Panel did not become ready")
                        time.sleep(0.2)
                client.post("/api/auth/login", json={"password": password}).raise_for_status()
                client.post("/api/pm/start").raise_for_status()
                response = client.get("/")
                response.raise_for_status()
                assert "text/html" in response.headers["content-type"]
                from curl_cffi.requests import Session

                with Session(impersonate="safari", trust_env=False) as browser:
                    assert browser.get(str(client.base_url), timeout=10).status_code == 200
                response = client.get("/api/sites/custom")
                response.raise_for_status()
                for kind in response.json()["types"].values():
                    assert kind["templates"], "Archived site templates are missing"
                response = client.post("/api/pm/stop")
                response.raise_for_status()
                assert not response.json()["running"]
            return round(time.monotonic() - started, 2)
        except Exception:
            log.flush()
            print((basedir / "panel.log").read_text(encoding="utf-8", errors="replace"))
            raise
        finally:
            if process.poll() is None:
                children = psutil.Process(process.pid).children(recursive=True)
                for child in children:
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                process.kill()
            process.wait(timeout=15)


def main():
    multiprocessing.set_start_method("spawn")
    import embykeeper
    import embykeeperapi
    import emoji
    import faker
    import pyrogram
    import telethon
    import tzdata

    for module in (embykeeper, embykeeperapi, emoji, faker, pyrogram, telethon, tzdata):
        assert "packages.zip" in module.__file__, module.__file__
    assert faker.Faker("zh_CN").name()
    assert emoji.replace_emoji("hello 😀") == "hello "
    assert pyrogram.raw.types.InputPeerUser(user_id=1, access_hash=2).write()
    assert bytes(telethon.tl.types.InputPeerUser(1, 2))
    from zoneinfo import TZPATH, ZoneInfo, available_timezones, reset_tzpath

    try:
        reset_tzpath(())
        assert datetime(2026, 1, 1, tzinfo=ZoneInfo("Asia/Shanghai")).utcoffset() == timedelta(hours=8)
        assert "America/New_York" in available_timezones()
    finally:
        reset_tzpath(TZPATH)
    from PIL import Image
    from embykeeperapi.app import _resolve_static_dir

    static = _resolve_static_dir()
    assert static and (static / "index.html").is_file()
    with Image.open(static / "tray.ico") as icon:
        assert icon.width > 0
    if sys.platform == "win32":
        import pystray

    asyncio.run(verify_ocr())
    with tempfile.TemporaryDirectory() as directory:
        elapsed = verify_panel(directory)
    print(json.dumps({"portable_smoke": "passed", "panel_cycle_seconds": elapsed}))


if __name__ == "__main__":
    main()
