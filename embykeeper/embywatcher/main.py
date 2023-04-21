import asyncio
import random
import string
from typing import Union
from datetime import datetime

from aiohttp import ClientError
from loguru import logger
from embypy.objects import Episode, Movie

from .emby import Emby, Connector, EmbyObject

logger = logger.bind(scheme="embywatcher")


class PlayError(Exception):
    pass


def _gen_random_device_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=16))


def is_ok(co):
    if isinstance(co, tuple):
        co, *_ = co
    if 200 <= co < 300:
        return True


async def get_oldest(emby: Emby, n=10):
    items = await emby.get_items(["Movie", "Episode"], limit=n, sort="DateCreated")
    i: Union[Movie, Episode]
    for i in items:
        yield i


async def set_played(obj: EmbyObject):
    c: Connector = obj.connector
    return is_ok(await c.post(f"/Users/{{UserId}}/PlayedItems/{obj.id}"))


async def hide_from_resume(obj: EmbyObject):
    c: Connector = obj.connector
    return is_ok(await c.post(f"/Users/{{UserId}}/Items/{obj.id}/HideFromResume", hide=True))


def get_last_played(obj: EmbyObject):
    last_played = obj.object_dict.get("UserData", {}).get("LastPlayedDate", None)
    return datetime.fromisoformat(last_played[:-2]) if last_played else None


async def send_playing(obj: EmbyObject, playing_info: dict):
    c: Connector = obj.connector
    try:
        while True:
            try:
                await asyncio.wait_for(c.post("/Sessions/Playing", **playing_info), 10)
            except (ClientError, ConnectionError, TimeoutError, asyncio.TimeoutError):
                pass
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        pass


async def play(obj: EmbyObject, time=800, progress=1000):
    c: Connector = obj.connector
    # 检查
    if obj.object_dict.get("RunTimeTicks") < max(progress, time) * 10000000:
        raise PlayError("视频长度低于观看进度所需")
    # 获取播放源
    resp = await c.postJson(f"/Items/{obj.id}/PlaybackInfo", isPlayBack=True, AutoOpenLiveStream=True)
    if not resp["MediaSources"]:
        raise PlayError("无视频源")
    else:
        play_session_id = resp["PlaySessionId"]
        media_source_id = resp["MediaSources"][0]["Id"]
    # 模拟播放
    playing_info = {
        "ItemId": obj.id,
        "PlayMethod": "DirectStream",
        "PlaySessionId": play_session_id,
        "MediaSourceId": media_source_id,
        "PositionTicks": 10000000 * progress,
        "CanSeek": True,
    }
    task = asyncio.create_task(send_playing(obj, playing_info))
    timeout = c.timeout
    try:
        c.timeout = time
        await c.get(
            f"/Videos/{obj.id}/stream",
            static=True,
            playSessionId=play_session_id,
            MediaSourceId=media_source_id,
        )
    except asyncio.TimeoutError:
        pass
    finally:
        c.timeout = timeout
        task.cancel()
    if not is_ok(await c.post("/Sessions/Playing/Stopped", **playing_info)):
        raise PlayError("无法正常结束播放")
    return True


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
        except ConnectionError:
            logger.error(f'Emby ({a["url"]}) 连接错误, 请重新检查配置.')
            continue

        if info:
            loggeruser = logger.bind(server=info["ServerName"], username=a["username"])
            loggeruser.info(f'成功登录 ({"Jellyfin" if a.get("jellyfin", False) else "Emby"} {info["Version"]}).')
            yield emby, a.get("time", 800), a.get("progress", 1000), loggeruser
        else:
            logger.error(f'Emby ({a["url"]}) 无法获取元信息而跳过, 请重新检查配置.')
            continue


async def watch(emby, time, progress, logger, retries=5):
    retry = 0
    while True:
        try:
            async for obj in get_oldest(emby):
                logger.info(f'开始尝试播放 "{obj.name}" ({time} 秒).')
                while True:
                    try:
                        if await play(obj, time, progress):
                            await obj.update()
                            if obj.play_count < 1:
                                raise PlayError("尝试播放后播放数低于1")
                            last_played = get_last_played(obj)
                            if not last_played:
                                raise PlayError("尝试播放后上次播放为空")
                            last_played = last_played.strftime("%Y-%m-%d %H:%M")
                            if not obj.percentage_played:
                                raise PlayError("尝试播放后播放进度为空")
                            logger.bind(notify="成功保活.").info(
                                f"[yellow]成功播放视频[/], 当前该视频播放{obj.play_count}次, 进度({obj.percentage_played}), 上次播放于 {last_played}."
                            )
                            return True
                    except (ClientError, OSError):
                        retry += 1
                        if retry > retries:
                            logger.warning(f"超过最大重试次数, 保活失败.")
                            return False
                        else:
                            logger.info(f"连接失败, 正在重试.")
                    except PlayError as e:
                        logger.info(f"发生错误: {e}, 正在重试其他视频.")
                        break
                    finally:
                        await hide_from_resume(obj)
            else:
                logger.warning(f"由于没有成功播放视频, 保活失败, 请重新检查配置.")
                return False
        except (ClientError, OSError):
            retry += 1
            if retry > retries:
                logger.warning(f"超过最大重试次数, 保活失败.")
                return False
            else:
                logger.info(f"连接失败, 正在重试.")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.opt(exception=e).warning("发生错误:")
            return False


async def watcher(config):
    async def wrapper(emby, time, progress, logger):
        try:
            return await asyncio.wait_for(watch(emby, time, progress, logger), max(time * 3, 180))
        except asyncio.TimeoutError:
            logger.warning(f"一定时间内未完成播放, 保活失败.")
            return False

    tasks = []
    async for emby, time, progress, logger in login(config):
        tasks.append(wrapper(emby, time, progress, logger))
    results = await asyncio.gather(*tasks)
    fails = len(tasks) - sum(results)
    if fails:
        logger.error(f"保活失败 ({fails}/{len(tasks)}).")
