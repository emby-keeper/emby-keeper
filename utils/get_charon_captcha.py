import asyncio
from pathlib import Path
from tqdm import tqdm, trange

from embykeeper.telegram.session import ClientsSession
from embykeeper.utils import AsyncTyper, async_partial
from embykeeper.config import config
from embykeeper import __name__ as __product__

app = AsyncTyper()

bot = "charontv_bot"
chat = "api_group"


@app.async_command()
async def generate(config_file: Path, num: int = 200, output: Path = "captchas.txt"):
    await config.reload_conf(config_file)
    async with ClientsSession(config.telegram.account[:1]) as clients:
        async for _, tg in clients:
            wr = async_partial(tg.wait_reply, bot, timeout=None)
            photos = []
            try:
                for _ in trange(num, desc="获取验证码"):
                    while True:
                        await asyncio.sleep(1)
                        msg = await wr("/cancel")
                        msg = await wr("/checkin")
                        if msg.caption and "请输入验证码" in msg.caption:
                            photos.append(msg.photo.file_id)
                            break
            finally:
                with open(output, "w+", encoding="utf-8") as f:
                    f.writelines(str(photo) + "\n" for photo in photos)


@app.async_command()
async def label(config_file: Path, inp: Path = "captchas.txt"):
    await config.reload_conf(config_file)
    with open(inp) as f:
        photos = [l.strip() for l in f.readlines()]
    tasks = []
    async with ClientsSession(config.telegram.account[:1]) as clients:
        async for _, tg in clients:
            for photo in tqdm(photos, desc="标记验证码"):
                async with tg.catch_reply(chat) as f:
                    await tg.send_photo(chat, photo)
                    labelmsg = await asyncio.wait_for(f, None)
                if not len(labelmsg.text) == 6:
                    continue
                else:
                    tasks.append(
                        asyncio.create_task(tg.download_media(photo, f"output/{labelmsg.text.lower()}.png"))
                    )
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    app()
