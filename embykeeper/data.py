import asyncio
import time
from typing import Iterable, Union

import aiofiles
import httpx
from cachetools import TTLCache
from loguru import logger

from .utils import format_byte_human, nonblocking, show_exception, to_iterable, get_proxy_str
from .config import config

logger = logger.bind(scheme="datamanager")

cdn_urls = [
    "https://raw.githubusercontent.com/emby-keeper/emby-keeper-data/main",
    "https://raw.gitmirror.com/emby-keeper/emby-keeper-data/main",
    "https://cdn.jsdelivr.net/gh/emby-keeper/emby-keeper-data",
]

versions = TTLCache(maxsize=128, ttl=600)
lock = asyncio.Lock()


async def refresh_version():
    async with nonblocking(lock):
        for data_url in cdn_urls:
            url = f"{data_url}/version"
            async with httpx.AsyncClient(
                http2=True, proxy=get_proxy_str(config.proxy), follow_redirects=True
            ) as client:
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        result = resp.text
                        for l in result.splitlines():
                            if l:
                                a, b = l.split("=")
                                versions[a.strip()] = b.strip()
                        break
                    else:
                        logger.warning(f"资源文件版本信息获取失败 ({resp.status_code})")
                        return False
                except httpx.HTTPError as e:
                    continue
                except Exception as e:
                    logger.warning(f"资源文件版本信息获取失败 ({e})")
                    show_exception(e)
                    return False
        else:
            logger.warning(f"资源文件版本信息获取失败.")
            return False


async def get_datas(names: Union[Iterable[str], str], caller: str = None):
    """
    获取额外数据.
    参数:
        names: 要下载的路径列表
        caller: 请求下载的模块名, 用于消息提示
    """

    basedir = config.basedir
    existing = {}
    not_existing = []
    for name in to_iterable(names):
        if (basedir / name).is_file():
            logger.debug(f'检测到请求的本地文件: "{name}".')
            existing[name] = basedir / name
        else:
            not_existing.append(name)

    if not_existing:
        logger.info(f"{caller or '该功能'} 正在下载或更新资源文件: {', '.join(not_existing)}")

    for name in to_iterable(names):
        version_matching = False
        while True:
            if (basedir / name).is_file():
                yield basedir / name
            else:
                try:
                    for data_url in cdn_urls:
                        url = f"{data_url}/data/{name}"
                        logger.debug(f"正在尝试 URL: {url}")
                        async with httpx.AsyncClient(
                            http2=True, proxy=get_proxy_str(config.proxy), follow_redirects=True
                        ) as client:
                            try:
                                resp = await client.get(url)
                                if resp.status_code == 200:
                                    file_size = int(resp.headers.get("content-length", 0))
                                    logger.info(f"开始下载: {name} ({format_byte_human(file_size)})")
                                    async with aiofiles.open(basedir / name, mode="wb+") as f:
                                        timer = time.time()
                                        length = 0
                                        async for chunk in resp.aiter_bytes(chunk_size=512):
                                            if time.time() - timer > 3:
                                                timer = time.time()
                                                logger.info(
                                                    f"正在下载: {name} ({format_byte_human(length)} / {format_byte_human(file_size)})"
                                                )
                                            await f.write(chunk)
                                            length += len(chunk)
                                    logger.info(f"下载完成: {name} ({format_byte_human(file_size)})")
                                    yield basedir / name
                                    break
                                elif resp.status_code in (403, 404) and not version_matching:
                                    await refresh_version()
                                    if name in versions:
                                        logger.debug(f'解析版本 "{name}" -> "{versions[name]}"')
                                        name = versions[name]
                                        version_matching = True
                                        break
                                    else:
                                        logger.warning(f"下载失败: {name} ({resp.status_code})")
                                        yield None
                                        break
                                else:
                                    logger.warning(f"下载失败: {name} ({resp.status_code})")
                                    yield None
                                    break
                            except httpx.HTTPError as e:
                                (basedir / name).unlink(missing_ok=True)
                                continue
                            except Exception as e:
                                (basedir / name).unlink(missing_ok=True)
                                logger.warning(f"下载失败: {name} ({e})")
                                show_exception(e)
                                yield None
                                break
                    else:
                        logger.warning(f"下载失败: {name}.")
                        yield None
                        continue
                except KeyboardInterrupt:
                    (basedir / name).unlink(missing_ok=True)
                    raise
            if not version_matching:
                break


async def get_data(name: str, caller: str = None):
    async for data in get_datas(name, caller):
        return data
