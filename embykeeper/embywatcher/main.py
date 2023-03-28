import asyncio
import random
import string

import asyncstdlib as ax
from aiohttp import ClientError
from loguru import logger

from .emby import Emby
from .watcher import EmbyWatcher

logger = logger.bind(scheme="embywatcher")


def _gen_random_device_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=16))


async def login(config):
    for a in config.get("emby", ()):
        logger.info(f'登录账号: {a["username"]} @ {a["url"]}')
        emby = Emby(
            url=a["url"],
            username=a["username"],
            password=a["password"],
            device_id=_gen_random_device_id(),
            jellyfin=a.get("jellyfin", False),
            proxy=config.get("proxy", None),
        )
        try:
            info = await emby.info()
            if info:
                loggeruser = logger.bind(server=info["ServerName"], username=a["username"])
                loggeruser.info(f'成功登录 ({"Jellyfin" if a.get("jellyfin", False) else "Emby"} {info["Version"]}).')
                yield emby, a.get("time", 800), a.get("progress", 1000), loggeruser
            else:
                logger.error(f'Emby ({a["url"]}) 无法获取元信息而跳过, 请重新检查配置.')
        except Exception as e:
            logger.error(f'Emby ({a["url"]}) maybe down.')


async def watch(emby, time, progress, logger):
    watcher = EmbyWatcher(emby)
    async for i, obj in ax.enumerate(watcher.get_oldest()):
        if i == 0:
            logger.info(f'开始尝试播放 "{obj.name}" ({time} 秒).')
        else:
            logger.info(f'发生错误, 重新开始尝试播放 "{obj.name}".')
        try:
            if await watcher.play(obj, time, progress):
                obj.update()
                if obj.play_count < 1:
                    continue
                last_played = watcher.get_last_played(obj)
                if not last_played:
                    continue
                last_played = last_played.strftime("%Y-%m-%d %H:%M")
                logger.info(f"[yellow]成功播放视频[/], 当前该视频播放{obj.play_count}次, 进度({obj.percentage_played}), 上次播放于 {last_played}.")
                break
        except KeyboardInterrupt as e:
            raise e from None
        except ClientError as e:
            continue
        except Exception as e:
            logger.opt(exception=e).warning('发生错误:')
        finally:
            watcher.hide_from_resume(obj)
    else:
        logger.warning(f"由于没有成功播放视频, 保活失败, 请重新检查配置.")
        return False
    return True


async def watcher(config):
    tasks = []
    async for emby, time, progress, logger in login(config):
        tasks.append(asyncio.create_task(watch(emby, time, progress, logger)))
    results = await asyncio.gather(*tasks)
    fails = len(tasks) - sum(results)
    if fails:
        logger.error(f"保活失败 ({fails}/{len(tasks)}).")
