from __future__ import annotations

import asyncio
from pathlib import Path
import random
import re
import string
from typing import TYPE_CHECKING, Iterable, Tuple, Union
from datetime import datetime, time, timezone
import uuid
import warnings
import json
import urllib.parse

import httpx
from loguru import logger
from dateutil import parser
from urllib.parse import urlparse
from faker import Faker

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from embypy.objects import Episode, Movie

from ..utils import show_exception, next_random_datetime, truncate_str
from ..var import debug
from .emby import Emby, Connector, EmbyObject

if TYPE_CHECKING:
    from loguru import Logger

logger = logger.bind(scheme="embywatcher")
cache_lock = asyncio.Lock()


class PlayError(Exception):
    pass


def is_ok(co):
    """判定返回来自 emby 的响应为成功."""
    if isinstance(co, tuple):
        co, *_ = co
    if 200 <= co < 300:
        return True


async def get_random_media(emby: Emby):
    """获取随机视频."""
    while True:
        items = await emby.get_items(["Movie", "Episode"], limit=3, sort="Random", ascending=False)
        i: Union[Movie, Episode]
        for i in items:
            yield i
        if not items:
            break


async def set_played(obj: EmbyObject):
    """设定已播放."""
    c: Connector = obj.connector
    return is_ok(await c.post(f"/Users/{{UserId}}/PlayedItems/{obj.id}"))


async def hide_from_resume(obj: EmbyObject):
    """从首页的"继续收看"部分隐藏."""
    c: Connector = obj.connector
    try:
        return is_ok(await c.post(f"/Users/{{UserId}}/Items/{obj.id}/HideFromResume", Hide=True))
    except RuntimeError:
        return False


def get_last_played(obj: EmbyObject):
    """获取上次播放时间."""
    last_played = obj.object_dict.get("UserData", {}).get("LastPlayedDate", None)
    return parser.parse(last_played) if last_played else None


async def play(obj: EmbyObject, loggeruser: Logger, time: float = 10):
    """模拟播放视频."""
    c: Connector = obj.connector

    await asyncio.sleep(random.uniform(1, 3))

    playback_info_data = {
        "DeviceProfile": {
            "CodecProfiles": [
                {
                    "ApplyConditions": [
                        {
                            "IsRequired": False,
                            "Value": "true",
                            "Condition": "NotEquals",
                            "Property": "IsAnamorphic",
                        },
                        {
                            "IsRequired": False,
                            "Value": "high|main|baseline|constrained baseline",
                            "Condition": "EqualsAny",
                            "Property": "VideoProfile",
                        },
                        {
                            "IsRequired": False,
                            "Value": "80",
                            "Condition": "LessThanEqual",
                            "Property": "VideoLevel",
                        },
                        {
                            "IsRequired": False,
                            "Value": "true",
                            "Condition": "NotEquals",
                            "Property": "IsInterlaced",
                        },
                    ],
                    "Type": "Video",
                    "Codec": "h264",
                },
                {
                    "ApplyConditions": [
                        {
                            "IsRequired": False,
                            "Value": "true",
                            "Condition": "NotEquals",
                            "Property": "IsAnamorphic",
                        },
                        {
                            "IsRequired": False,
                            "Value": "high|main|main 10",
                            "Condition": "EqualsAny",
                            "Property": "VideoProfile",
                        },
                        {
                            "IsRequired": False,
                            "Value": "175",
                            "Condition": "LessThanEqual",
                            "Property": "VideoLevel",
                        },
                        {
                            "IsRequired": False,
                            "Value": "true",
                            "Condition": "NotEquals",
                            "Property": "IsInterlaced",
                        },
                    ],
                    "Type": "Video",
                    "Codec": "hevc",
                },
            ],
            "SubtitleProfiles": [
                {"Method": "Embed", "Format": "ass"},
                {"Method": "Embed", "Format": "ssa"},
                {"Method": "Embed", "Format": "subrip"},
                {"Method": "Embed", "Format": "sub"},
                {"Method": "Embed", "Format": "pgssub"},
                {"Method": "External", "Format": "subrip"},
                {"Method": "External", "Format": "sub"},
                {"Method": "External", "Format": "ass"},
                {"Method": "External", "Format": "ssa"},
                {"Method": "External", "Format": "vtt"},
                {"Method": "External", "Format": "ass"},
                {"Method": "External", "Format": "ssa"},
            ],
            "MaxStreamingBitrate": 40000000,
            "DirectPlayProfiles": [
                {
                    "Container": "mov,mp4,mkv,webm",
                    "Type": "Video",
                    "VideoCodec": "h264,hevc,dvhe,dvh1,h264,hevc,hev1,mpeg4,vp9",
                    "AudioCodec": "aac,mp3,wav,ac3,eac3,flac,truehd,dts,dca,opus",
                }
            ],
            "TranscodingProfiles": [
                {
                    "MinSegments": 2,
                    "AudioCodec": "aac,mp3,wav,ac3,eac3,flac,opus",
                    "VideoCodec": "hevc,h264,mpeg4",
                    "BreakOnNonKeyFrames": True,
                    "Type": "Video",
                    "Protocol": "hls",
                    "MaxAudioChannels": "6",
                    "Container": "ts",
                    "Context": "Streaming",
                }
            ],
            "ContainerProfiles": [],
            "MusicStreamingTranscodingBitrate": 40000000,
            "ResponseProfiles": [{"MimeType": "video\/mp4", "Container": "m4v", "Type": "Video"}],
            "MaxStaticBitrate": 40000000,
        }
    }

    resp = await c.getJson(
        f"/Videos/{obj.id}/AdditionalParts",
        Fields="PrimaryImageAspectRatio,UserData,CanDelete",
        IncludeItemTypes="Playlist,BoxSet",
        Recursive=True,
        SortBy="SortName",
    )

    resp = await c.postJson(
        f"/Items/{obj.id}/PlaybackInfo",
        AutoOpenLiveStream=False,
        IsPlayback=False,
        MaxStreamingBitrate=40000000,
        StartTimeTicks=0,
        UserID=c.userid,
        data=playback_info_data,
    )
    play_session_id = resp.get("PlaySessionId", "")
    if "MediaSources" in resp:
        media_source_id = resp["MediaSources"][0]["Id"]
        direct_stream_url = resp["MediaSources"][0].get("DirectStreamUrl", None)
    else:
        media_source_id = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(32))
        direct_stream_url = None

    await asyncio.sleep(random.uniform(1, 3))

    # 模拟播放
    for i in range(4):
        if i:
            IsPlayback = True
            AutoOpenLiveStream = True
        else:
            IsPlayback = False
            AutoOpenLiveStream = False
        resp = await c.postJson(
            f"/Items/{obj.id}/PlaybackInfo",
            AutoOpenLiveStream=AutoOpenLiveStream,
            IsPlayback=IsPlayback,
            MaxStreamingBitrate=42000000,
            StartTimeTicks=0,
            UserID=c.userid,
            data=playback_info_data,
        )

    def get_playing_data(tick, update=False, stop=False):
        data = {
            "SubtitleOffset": 0,
            "MaxStreamingBitrate": 420000000,
            "MediaSourceId": str(media_source_id),
            "SubtitleStreamIndex": -1,
            "VolumeLevel": 100,
            "PlaybackRate": 1,
            "PlaybackStartTimeTicks": datetime.now().timestamp() * 10000000,
            "PositionTicks": tick,
            "PlaySessionId": play_session_id,
        }
        if update:
            data["EventName"] = "timeupdate"
        if stop:
            queue = []
        else:
            queue = [{"Id": str(obj.id), "PlaylistItemId": "playlistItem0"}]
        data.update(
            {
                "PlaylistLength": 1,
                "NowPlayingQueue": queue,
                "IsMuted": False,
                "PlaylistIndex": 0,
                "ItemId": str(obj.id),
                "RepeatMode": "RepeatNone",
                "AudioStreamIndex": -1,
                "PlayMethod": "DirectStream",
                "CanSeek": True,
                "IsPaused": True,
            }
        )
        return data

    play_headers = {
        "User-Agent": "VLC/3.0.21 LibVLC/3.0.21",
        "X-Playback-Session-Id": play_session_id,
    }
    task = asyncio.create_task(
        c.get_stream_noreturn(direct_stream_url or f"/Videos/{obj.id}/stream", headers=play_headers)
    )
    Connector.playing_count += 1
    try:
        await asyncio.sleep(random.uniform(1, 3))

        resp = await c.post("Sessions/Playing", data=get_playing_data(0))

        if not is_ok(resp):
            raise PlayError("无法开始播放")
        t = time
        last_report_t = t
        progress_errors = 0
        while t > 0:
            if progress_errors > 12:
                raise PlayError("播放状态设定错误次数过多")
            if last_report_t and last_report_t - t > (5 if debug else 30):
                loggeruser.info(f'正在播放: "{truncate_str(obj.name, 10)}" (还剩 {t:.0f} 秒).')
                last_report_t = t
            st = min(10, t)
            await asyncio.sleep(st)
            t -= st
            tick = int((time - t) * 10000000)
            payload = get_playing_data(tick, update=True)
            try:
                resp = await asyncio.wait_for(c.post("/Sessions/Playing/Progress", data=payload), 10)
            except (httpx.HTTPError, asyncio.TimeoutError) as e:
                loggeruser.debug(f"播放状态设定错误: {e}")
                progress_errors += 1
            else:
                if not is_ok(resp):
                    loggeruser.debug(f"播放状态设定错误: {resp}")
                    progress_errors += 1
        await asyncio.sleep(random.uniform(1, 3))
    finally:
        Connector.playing_count -= 1
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            loggeruser.warning(f"模拟播放时, 访问流媒体文件失败.")
            show_exception(e)

    for retry in range(3):
        try:
            if not is_ok(
                await c.post("/Sessions/Playing/Stopped", data=get_playing_data(time * 10000000, stop=True))
            ):
                if retry == 2:
                    raise PlayError("尝试停止播放3次后仍然失败")
                loggeruser.debug(f"停止播放失败，正在进行第 {retry + 1}/3 次尝试")
                await asyncio.sleep(1)
                continue
            else:
                loggeruser.info(f"播放完成, 共 {time:.0f} 秒.")
                return True
        except httpx.HTTPError as e:
            if retry == 2:
                raise PlayError(f"由于连接错误或服务器错误无法停止播放: {e}")
            loggeruser.debug(f"停止播放时发生连接错误或服务器错误，正在进行第 {retry + 1}/3 次尝试: {e}")
            await asyncio.sleep(1)


async def get_cf_clearance(config, url, user_agent=None):
    from embykeeper.telechecker.link import Link
    from embykeeper.telechecker.tele import ClientsSession
    from embykeeper.resocks import Resocks

    server_info_url = f"{url.rstrip('/')}"
    telegrams = config.get("telegram", [])
    if not len(telegrams):
        logger.warning(f"未设置 Telegram 账号, 无法为 Emby 站点使用验证码解析.")
    async with ClientsSession.from_config(config) as clients:
        async for tg in clients:
            rid, host, key = await Link(tg).resocks()
            if not rid:
                return None
            resocks = Resocks(config["basedir"])
            try:
                if not await resocks.start(host, key):
                    logger.warning(f"连接到反向代理服务器失败.")
                    return None
                cf_clearance, _ = await Link(tg).captcha_resocks(rid, server_info_url, user_agent)
            finally:
                resocks.stop()
            return cf_clearance
    return None


def get_device_uuid():
    rd = random.Random()
    rd.seed(uuid.getnode())
    return uuid.UUID(int=rd.getrandbits(128))


def get_random_device():
    device_type = random.choice(("iPhone", "iPad"))

    # All patterns with their weights
    patterns = [
        ("chinese_normal", 20),
        ("chinese_lastname_pinyin", 40),
        ("chinese_firstname_pinyin", 10),
        ("english_normal", 20),
        ("english_upper", 10),
        ("english_name_only", 10),
    ]

    pattern = random.choices([p[0] for p in patterns], weights=[p[1] for p in patterns])[0]

    if pattern.startswith("chinese"):
        fake = Faker("zh_CN")
        surname = fake.last_name()
        given_name = fake.first_name_male() if random.random() < 0.5 else fake.first_name_female()

        if pattern == "chinese_normal":
            return f"{surname}{given_name}的{device_type}"
        else:
            from xpinyin import Pinyin

            p = Pinyin()
            if pattern == "chinese_lastname_pinyin":
                pinyin = p.get_pinyin(surname).capitalize()
                return f"{pinyin}的{device_type}"
            else:  # chinese_firstname_pinyin
                pinyin = "".join([word[0].upper() for word in p.get_pinyin(given_name).split("-")])
                return f"{pinyin}的{device_type}"
    else:
        fake = Faker("en_US")
        name = fake.first_name()

        if pattern == "english_normal":
            return f"{name}'s {device_type}"
        elif pattern == "english_upper":
            return f"{name.upper()}{device_type.upper()}"
        else:  # english_name_only
            return name


async def get_fake_headers(
    basedir: Path,
    hostname: str,
    client: str = None,
    device: str = None,
    device_id: str = None,
    client_version: str = None,
    ua: str = None,
):
    headers = {}
    cache_dir = basedir / "emby_headers"
    cache_file = cache_dir / f"{hostname}.json"

    async with cache_lock:
        cache_dir.mkdir(exist_ok=True, parents=True)
        cached_headers = {}
        if cache_file.exists():
            try:
                cached_headers = json.loads(cache_file.read_text())
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"读取 Emby 请求头缓存失败: {e}")

    # 按优先级获取各个值
    client = client or cached_headers.get("client") or "Fileball"
    device = device or cached_headers.get("device") or get_random_device()
    device_id = device_id or cached_headers.get("device_id") or str(get_device_uuid()).upper()
    version = client_version or cached_headers.get("client_version") or f"1.3.{random.randint(28, 30)}"
    ua = ua or cached_headers.get("ua") or f"Fileball/{version}"

    # 构建认证头
    auth_headers = {
        "Client": client,
        "Device": device,
        "DeviceId": device_id,
        "Version": version,
    }
    auth_header = ",".join([f"{k}={urllib.parse.quote(str(v))}" for k, v in auth_headers.items()])

    # 构建完整请求头
    headers["User-Agent"] = ua
    headers["Accept-Language"] = "zh-CN,zh-Hans;q=0.9"
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "*/*"

    # 保存到缓存
    async with cache_lock:
        try:
            cache_data = {
                "client": client,
                "device": device,
                "device_id": device_id,
                "client_version": version,
                "ua": ua,
            }
            cache_file.write_text(json.dumps(cache_data, indent=2))
        except OSError as e:
            logger.debug(f"保存 headers 缓存失败: {e}")

    return headers, auth_header


async def login(config, continuous=None, per_site=None):
    """登录账号."""

    for a in config.get("emby", ()):
        if (continuous is not None) and (not continuous == a.get("continuous", False)):
            continue
        use_per_site = bool(a.get("watchtime", None)) or bool(a.get("interval", None))
        if (per_site is not None) and (not per_site == use_per_site):
            continue
        logger.info(f'登录账号: "{a["username"]}" 至服务器: "{a["url"]}"')

        info = None
        for _ in range(3):
            cf_clearance = None

            device_id = a.get("device_id", None)
            basedir = Path(config["basedir"])
            if not device_id:
                device_id_file = basedir / "emby_device_id"
                if device_id_file.exists():
                    try:
                        device_id = device_id_file.read_text().strip()
                    except OSError as e:
                        logger.debug(f"读取 device_id 文件失败: {e}")
                if not device_id:
                    device_id = str(get_device_uuid()).upper()
                    try:
                        device_id_file.write_text(device_id)
                    except OSError as e:
                        logger.debug(f"保存 device_id 文件失败: {e}")

            if not a["password"]:
                logger.warning(f'Emby "{a["url"]}" 未设置密码, 可能导致登陆失败.')

            hostname = urlparse(a["url"]).netloc
            headers, auth_header = await get_fake_headers(
                basedir=basedir,
                hostname=hostname,
                ua=a.get("ua", None),
                device=a.get("device", None),
                client=a.get("client", None),
                client_version=a.get("client_version", None),
                device_id=device_id,
            )

            emby = Emby(
                url=a["url"],
                username=a["username"],
                password=a["password"],
                jellyfin=a.get("jellyfin", False),
                proxy=config.get("proxy", None) if a.get("use_proxy", True) else None,
                headers=headers,
                basedir=basedir,
                auth_header=auth_header,
                cf_clearance=cf_clearance,
            )
            try:
                info = await emby.info()
            except httpx.HTTPError as e:
                if "Unexpected JSON output" in str(e):
                    if "cf-wrapper" in str(e) or "Enable JavaScript and cookies to continue" in str(e):
                        if a.get("cf_challenge", False):
                            logger.info(f'Emby "{a["url"]}" 已启用 Cloudflare 保护, 即将请求解析.')
                            cf_clearance = await get_cf_clearance(config, a["url"], a.get("ua", None))
                            if not cf_clearance:
                                logger.warning(f'Emby "{a["url"]}" 验证码解析失败而跳过.')
                                break
                        else:
                            if config.get("proxy", None):
                                logger.warning(
                                    f'Emby "{a["url"]}" 已启用 Cloudflare 保护, 请尝试浏览器以同样的代理访问: {a["url"]} 以解除 Cloudflare IP 限制, 然后再次运行.'
                                )
                            else:
                                logger.warning(
                                    f'Emby "{a["url"]}" 已启用 Cloudflare 保护, 请使用 "cf_challenge" 配置项以允许尝试解析验证码.'
                                )
                            break
                    else:
                        logger.error(f'Emby ({a["url"]}) 连接错误或服务器错误, 请重新检查配置: {e}')
                        break
                else:
                    logger.error(f'Emby ({a["url"]}) 连接错误或服务器错误, 请重新检查配置: {e}')
                    break
            else:
                break
        else:
            logger.warning(f'Emby "{a["url"]}" 验证码解析次数过多而跳过.')

        if info:
            loggeruser = logger.bind(server=info["ServerName"], username=a["username"])
            loggeruser.info(
                f'成功连接至服务器 "{a["url"]}" ({"Jellyfin" if a.get("jellyfin", False) else "Emby"} {info["Version"]}).'
            )
            yield (
                emby,
                loggeruser,
                a.get("time", None if continuous else [120, 240]),
                True if continuous else a.get("allow_multiple", True),
                a.get("allow_stream", False),
                a.get("hide", False),
            )
        else:
            logger.bind(log=True).error(f'Emby "{a["url"]}" 无法获取元信息而跳过, 请重新检查配置.')
            continue


async def watch(
    emby: Emby,
    loggeruser: Logger,
    time: Union[float, Tuple[float, float]],
    stream: bool = False,
    hide: bool = False,
    retries: int = 5,
):
    """
    主执行函数 - 观看一个视频.
    参数:
        emby: Emby 客户端
        time: 模拟播放时间
        progress: 播放后设定的观看进度
        loggeruser: 日志器
        retries: 最大重试次数
    """
    retry = 0
    while True:
        try:
            async for obj in get_random_media(emby):
                if isinstance(time, int) and time <= 0:
                    loggeruser.info(f"需要播放的时间小于0, 仅登陆.")
                    return True
                if isinstance(time, Iterable):
                    t = random.uniform(*time) + 10
                else:
                    t = time + 10
                total_ticks = obj.object_dict.get("RunTimeTicks")
                if not total_ticks:
                    if not stream:
                        rt = random.uniform(30, 60)
                        loggeruser.info(
                            f'无法获取视频 "{truncate_str(obj.name, 10)}" 长度, 等待 {rt:.0f} 秒后重试.'
                        )
                        await asyncio.sleep(rt)
                        continue
                loggeruser.info(f'开始尝试播放 "{truncate_str(obj.name, 10)}" ({t:.0f} 秒).')
                while True:
                    try:
                        await play(obj, loggeruser, time=t)

                        obj = await obj.update("UserData")

                        if obj.play_count < 1:
                            raise PlayError("尝试播放后播放数低于1")

                        last_played = get_last_played(obj)
                        if not last_played:
                            raise PlayError("尝试播放后无记录")

                        last_played = (
                            last_played.replace(tzinfo=timezone.utc)
                            .astimezone(tz=None)
                            .strftime("%m-%d %H:%M")
                        )

                        prompt = (
                            f"[yellow]成功播放视频[/], "
                            + f"当前该视频播放 {obj.play_count} 次, "
                            + f"上次播放于 {last_played} UTC."
                        )

                        loggeruser.bind(log=True).info(prompt)
                        return True
                    except httpx.HTTPError as e:
                        retry += 1
                        if retry > retries:
                            loggeruser.warning(f"超过最大重试次数, 保活失败: {e}.")
                            return False
                        else:
                            rt = random.uniform(30, 60)
                            loggeruser.info(f"连接失败或服务器错误, 等待 {rt:.0f} 秒后重试: {e}.")
                            await asyncio.sleep(rt)
                    except PlayError as e:
                        retry += 1
                        if retry > retries:
                            loggeruser.warning(f"超过最大重试次数, 保活失败: {e}.")
                            return False
                        else:
                            rt = random.uniform(30, 60)
                            loggeruser.info(f"发生错误, 等待 {rt:.0f} 秒后重试其他视频: {e}.")
                            await asyncio.sleep(rt)
                        break
                    finally:
                        if hide:
                            try:
                                if not await asyncio.shield(asyncio.wait_for(hide_from_resume(obj), 5)):
                                    loggeruser.debug(f"未能成功从最近播放中隐藏视频.")
                                else:
                                    loggeruser.info(f"已从最近播放中隐藏该视频.")
                            except asyncio.TimeoutError:
                                loggeruser.debug(f"从最近播放中隐藏视频超时.")
            else:
                loggeruser.warning(f"由于没有获取到可播放视频, 保活失败, 请重新检查配置.")
                return False
        except httpx.HTTPError as e:
            retry += 1
            if retry > retries:
                loggeruser.warning(f"超过最大重试次数, 保活失败: {e}.")
                return False
            else:
                rt = random.uniform(30, 60)
                loggeruser.info(f"连接失败, 等待 {rt:.0f} 秒后重试: {e}.")
                await asyncio.sleep(rt)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            loggeruser.warning(f"发生错误, 保活失败.")
            show_exception(e, regular=False)
            return False


async def watch_multiple(
    emby: Emby,
    loggeruser: Logger,
    time: Union[float, Tuple[float, float]],
    stream: bool = False,
    hide: bool = False,
    retries: int = 5,
):
    if isinstance(time, Iterable):
        req_time = random.uniform(*time) + 10
    else:
        req_time = time + 10
    if not (isinstance(time, int) and time <= 0):
        loggeruser.info(f"开始播放视频 (允许播放多个), 共需播放 {req_time:.0f} 秒.")
    played_time = 0
    played_videos = 0
    retry = 0
    while True:
        try:
            async for obj in get_random_media(emby):
                if isinstance(time, int) and time <= 0:
                    loggeruser.info(f"需要播放的时间小于0, 仅登陆.")
                    return True
                total_ticks = obj.object_dict.get("RunTimeTicks")
                if not total_ticks:
                    if stream:
                        total_ticks = min(req_time, random.randint(480, 720)) * 10000000
                    else:
                        rt = random.uniform(30, 60)
                        loggeruser.info(
                            f'无法获取视频 "{truncate_str(obj.name, 10)}" 长度, 等待 {rt:.0f} 秒后重试.'
                        )
                        await asyncio.sleep(rt)
                        continue
                total_time = total_ticks / 10000000
                if req_time - played_time > total_time:
                    play_time = total_time
                else:
                    play_time = max(req_time - played_time, 10)
                loggeruser.info(f'开始尝试播放 "{truncate_str(obj.name, 10)}" ({play_time:.0f} 秒).')
                while True:
                    try:
                        await play(obj, loggeruser, time=play_time)

                        obj = await obj.update("UserData")

                        if obj.play_count < 1:
                            raise PlayError("尝试播放后播放数低于1")

                        last_played = get_last_played(obj)
                        if not last_played:
                            raise PlayError("尝试播放后无记录")

                        last_played = (
                            last_played.replace(tzinfo=timezone.utc)
                            .astimezone(tz=None)
                            .strftime("%m-%d %H:%M")
                        )

                        prompt = (
                            f"[yellow]成功播放视频[/], "
                            + f"当前该视频播放 {obj.play_count} 次, "
                            + f"上次播放于 {last_played} UTC."
                        )
                        loggeruser.info(prompt)
                        played_videos += 1
                        played_time += play_time

                        if played_time >= req_time - 1:
                            loggeruser.bind(log=True).info(f"保活成功, 共播放 {played_videos} 个视频.")
                            return True
                        else:
                            loggeruser.info(f"还需播放 {req_time - played_time:.0f} 秒.")
                            rt = random.uniform(5, 15)
                            loggeruser.info(f"等待 {rt:.0f} 秒后播放下一个.")
                            await asyncio.sleep(rt)
                            break
                    except httpx.HTTPError as e:
                        retry += 1
                        if retry > retries:
                            loggeruser.warning(f"超过最大重试次数, 保活失败: {e}.")
                            return False
                        else:
                            rt = random.uniform(30, 60)
                            loggeruser.info(f"连接失败, 等待 {rt:.0f} 秒后重试: {e}.")
                            await asyncio.sleep(rt)
                    except PlayError as e:
                        retry += 1
                        if retry > retries:
                            loggeruser.warning(f"超过最大重试次数, 保活失败: {e}.")
                            return False
                        else:
                            rt = random.uniform(30, 60)
                            loggeruser.info(f"发生错误, 等待 {rt:.0f} 秒后重试其他视频: {e}.")
                            await asyncio.sleep(rt)
                        break
                    finally:
                        if hide:
                            try:
                                if not await asyncio.shield(asyncio.wait_for(hide_from_resume(obj), 5)):
                                    loggeruser.debug(f"未能成功从最近播放中隐藏视频.")
                                else:
                                    loggeruser.info(f"已从最近播放中隐藏该视频.")
                            except asyncio.TimeoutError:
                                loggeruser.debug(f"从最近播放中隐藏视频超时.")
            else:
                loggeruser.warning(f"由于没有成功播放视频, 保活失败, 请重新检查配置.")
                return False
        except httpx.HTTPError as e:
            retry += 1
            if retry > retries:
                loggeruser.warning(f"超过最大重试次数, 保活失败: {e}.")
                return False
            else:
                rt = random.uniform(30, 60)
                loggeruser.info(f"连接失败, 等待 {rt:.0f} 秒后重试: {e}.")
                await asyncio.sleep(rt)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            loggeruser.warning(f"发生错误, 保活失败.")
            show_exception(e, regular=False)
            return False


async def watch_continuous(emby: Emby, loggeruser: Logger, stream: bool = False, hide: bool = False):
    """
    主执行函数 - 持续观看.

    参数:
        emby: Emby 客户端
        loggeruser: 日志器
        stream: 是否允许流媒体
        hide: 是否从继续收看中隐藏
    """
    while True:
        try:
            async for obj in get_random_media(emby):
                total_ticks = obj.object_dict.get("RunTimeTicks")
                if not total_ticks:
                    if stream:
                        loggeruser.warning('"allow_stream" 无法与 "continuous" 共用, 因此已被忽略.')
                    rt = random.uniform(30, 60)
                    loggeruser.info(f"无法获取视频长度, 等待 {rt:.0f} 秒后重试.")
                    await asyncio.sleep(rt)
                    continue
                total_time = total_ticks / 10000000
                loggeruser.info(f'开始尝试播放 "{truncate_str(obj.name, 10)}" (长度 {total_time:.0f} 秒).')
                try:
                    await play(obj, loggeruser, time=total_time)
                except PlayError as e:
                    rt = random.uniform(30, 60)
                    loggeruser.info(f"发生错误, 等待 {rt:.0f} 秒后重试: {e}.")
                    await asyncio.sleep(rt)
                    continue
                finally:
                    if hide:
                        try:
                            if not await asyncio.shield(asyncio.wait_for(hide_from_resume(obj), 2)):
                                loggeruser.debug(f"未能成功从最近播放中隐藏视频.")
                            else:
                                loggeruser.info(f"已从最近播放中隐藏该视频.")
                        except asyncio.TimeoutError:
                            loggeruser.debug(f"从最近播放中隐藏视频超时.")
        except httpx.HTTPError as e:
            rt = random.uniform(30, 60)
            loggeruser.info(f"连接失败, 等待 {rt:.0f} 秒后重试: {e}.")
            await asyncio.sleep(rt)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            loggeruser.warning(f"发生错误, 停止持续播放.")
            show_exception(e, regular=False)
            return False


async def watcher(config: dict, instant: bool = False, per_site: bool = None):
    """入口函数 - 观看一个视频."""

    async def wrapper(
        sem: asyncio.Semaphore,
        emby: Emby,
        loggeruser: Logger,
        time: float,
        multiple: bool,
        stream: bool,
        hide: bool,
    ):
        async with sem:
            try:
                if not instant:
                    wait = random.uniform(180, 360)
                    loggeruser.info(f"播放视频前随机等待 {wait:.0f} 秒.")
                    await asyncio.sleep(wait)
                if isinstance(time, Iterable):
                    tm = max(time) * 4
                else:
                    tm = time * 4
                if multiple:
                    return await asyncio.wait_for(
                        watch_multiple(emby, loggeruser, time, stream, hide), max(tm, 600)
                    )
                else:
                    return await asyncio.wait_for(watch(emby, loggeruser, time, stream, hide), max(tm, 600))
            except asyncio.TimeoutError:
                loggeruser.warning(f"一定时间内未完成播放, 保活失败.")
                return False

    if not per_site:
        logger.info("开始执行 Emby 保活.")
    tasks = []
    concurrent = int(config.get("watch_concurrent", 3))
    if not concurrent:
        concurrent = 100000
    sem = asyncio.Semaphore(concurrent)
    async for emby, loggeruser, time, multiple, stream, hide in login(
        config, per_site=per_site, continuous=False
    ):
        tasks.append(wrapper(sem, emby, loggeruser, time, multiple, stream, hide))
    if not per_site:
        if not tasks:
            logger.info("没有指定相关的 Emby 服务器, 跳过保活.")
    results = await asyncio.gather(*tasks)
    fails = len(tasks) - sum(results)
    if not per_site:
        if fails:
            logger.error(f"保活失败 ({fails}/{len(tasks)}).")
    return not fails


async def watcher_schedule(
    config: dict,
    start_time=time(11, 0),
    end_time=time(23, 0),
    days: Union[int, Tuple[int, int]] = 7,
    instant: bool = False,
):
    """计划任务 - 启动所有站点的一次观看."""

    timestamp_file = Path(config["basedir"]) / "watcher_schedule_next_timestamp"
    current_config = {
        "start_time": start_time.strftime("%H:%M"),
        "end_time": end_time.strftime("%H:%M"),
        "days": days if isinstance(days, int) else list(days),
    }

    while True:
        next_dt = None
        config_changed = False

        if timestamp_file.exists():
            try:
                stored_data = json.loads(timestamp_file.read_text())
                if not isinstance(stored_data, dict):
                    raise ValueError("invalid cache")
                stored_timestamp = stored_data["timestamp"]
                stored_config = stored_data["config"]

                if stored_config != current_config:
                    logger.info("计划任务配置已更改，将重新计算下次执行时间.")
                    config_changed = True
                else:
                    next_dt = datetime.fromtimestamp(stored_timestamp)
                    if next_dt > datetime.now():
                        logger.bind(log=True).info(
                            f"从缓存中读取到下次保活时间: {next_dt.strftime('%m-%d %H:%M %p')}."
                        )
            except (ValueError, OSError, json.JSONDecodeError) as e:
                logger.debug(f"读取存储的时间戳失败: {e}")
                config_changed = True

        if not next_dt or next_dt <= datetime.now() or config_changed:
            if isinstance(days, int):
                rand_days = days
            else:
                rand_days = random.randint(*days)
            next_dt = next_random_datetime(start_time, end_time, interval_days=rand_days)
            logger.bind(log=True).info(f"下一次保活将在 {next_dt.strftime('%m-%d %H:%M %p')} 进行.")

            try:
                save_data = {"timestamp": next_dt.timestamp(), "config": current_config}
                timestamp_file.write_text(json.dumps(save_data))
            except OSError as e:
                logger.debug(f"存储时间戳失败: {e}")

        await asyncio.sleep((next_dt - datetime.now()).total_seconds())
        try:
            timestamp_file.unlink(missing_ok=True)
        except OSError as e:
            logger.debug(f"删除时间戳文件失败: {e}")
        await watcher(config, instant=instant, per_site=False)


async def watcher_schedule_site(config: dict, instant: bool = False):
    """计划任务 - 启动各某个站点的一次观看."""

    async def site_schedule(site_config: dict):
        site_url = site_config["url"]

        watchtime = site_config.get("watchtime", None)
        interval = site_config.get("interval", None)

        if not watchtime and not interval:
            return
        else:
            if not watchtime:
                watchtime = config.get("watchtime", "<11:00AM,11:00PM>")
            if not interval:
                interval = config.get("interval", "<3,12>")

        watchtime_match = re.match(r"<\s*(.*),\s*(.*)\s*>", watchtime)
        if watchtime_match:
            start_time, end_time = [parser.parse(watchtime_match.group(i)).time() for i in (1, 2)]
        else:
            start_time = end_time = parser.parse(watchtime).time()

        if interval and not isinstance(interval, int):
            try:
                interval = abs(int(interval))
            except ValueError:
                interval_range_match = re.match(r"<(\d+),(\d+)>", interval)
                if interval_range_match:
                    interval = [int(interval_range_match.group(1)), int(interval_range_match.group(2))]
                else:
                    logger.error(
                        f'站点 "{site_url}": 无法解析 Emby 保活间隔天数: {interval}, 保活将不会运行.'
                    )
                    return False

        # 将 URL 转换为 site_name: 去除协议前缀，替换所有符号为下划线，合并连续下划线
        site_name = re.sub(r"^https?://", "", site_url)  # 移除 http:// 或 https://
        site_name = re.sub(r"[^\w\s]", "_", site_name)  # 将所有非字母数字字符替换为下划线
        site_name = re.sub(r"_+", "_", site_name)  # 将多个连续下划线替换为单个
        site_name = site_name.strip("_")  # 移除开头和结尾的下划线

        timestamp_file = Path(config["basedir"]) / f"watcher_schedule_next_timestamp_{site_name}"
        current_config = {
            "start_time": start_time.strftime("%H:%M"),
            "end_time": end_time.strftime("%H:%M"),
            "days": interval if isinstance(interval, int) else list(interval),
        }

        while True:
            next_dt = None
            config_changed = False

            if timestamp_file.exists():
                try:
                    stored_data = json.loads(timestamp_file.read_text())
                    if not isinstance(stored_data, dict):
                        raise ValueError("invalid cache")
                    stored_timestamp = stored_data["timestamp"]
                    stored_config = stored_data["config"]

                    if stored_config != current_config:
                        logger.info(f'站点 "{site_url}": 计划任务配置已更改，将重新计算下次执行时间.')
                        config_changed = True
                    else:
                        next_dt = datetime.fromtimestamp(stored_timestamp)
                        if next_dt > datetime.now():
                            logger.bind(log=True).info(
                                f'站点 "{site_url}": 从缓存中读取到下次保活时间: {next_dt.strftime("%m-%d %H:%M %p")}.'
                            )
                except (ValueError, OSError, json.JSONDecodeError) as e:
                    logger.debug(f'站点 "{site_url}": 读取存储的时间戳失败: {e}')
                    config_changed = True

            if not next_dt or next_dt <= datetime.now() or config_changed:
                if isinstance(interval, int):
                    rand_days = interval
                else:
                    rand_days = random.randint(*interval)
                next_dt = next_random_datetime(start_time, end_time, interval_days=rand_days)
                logger.bind(log=True).info(
                    f'站点 "{site_url}": 下一次保活将在 {next_dt.strftime("%m-%d %H:%M %p")} 进行.'
                )

                try:
                    save_data = {"timestamp": next_dt.timestamp(), "config": current_config}
                    timestamp_file.write_text(json.dumps(save_data))
                except OSError as e:
                    logger.debug(f'站点 "{site_url}": 存储时间戳失败: {e}')

            await asyncio.sleep((next_dt - datetime.now()).total_seconds())
            try:
                timestamp_file.unlink(missing_ok=True)
            except OSError as e:
                logger.debug(f'站点 "{site_url}": 删除时间戳文件失败: {e}')

            filtered_config = config.copy()
            filtered_config["emby"] = [site_config]

            return await watcher(filtered_config, instant=instant, per_site=True)

    tasks = []
    for site_config in config.get("emby", []):
        tasks.append(site_schedule(site_config))
    return await asyncio.gather(*tasks)


async def watcher_continuous(config: dict):
    """入口函数 - 持续观看."""

    async def wrapper(emby: Emby, loggeruser: Logger, time: float, stream: bool, hide: bool):
        if time:
            if isinstance(time, Iterable):
                time = random.uniform(*time)
            loggeruser.info(f"即将连续播放视频, 持续 {time:.0f} 秒.")
        else:
            loggeruser.info(f"即将无限连续播放视频.")
        try:
            await asyncio.wait_for(watch_continuous(emby, loggeruser, stream, hide), time)
        except asyncio.TimeoutError:
            loggeruser.info(f"连续播放结束, 将在明天继续连续播放.")
            return True
        else:
            return False

    logger.info("开始执行 Emby 持续观看.")
    tasks = []
    async for emby, loggeruser, time, _, stream, hide in login(config, continuous=True, per_site=False):
        tasks.append(wrapper(emby, loggeruser, time, stream, hide))
    if not tasks:
        logger.info("没有指定相关的 Emby 服务器, 跳过持续观看.")
    return await asyncio.gather(*tasks)


async def watcher_continuous_schedule(
    config: dict, start_time=time(11, 0), end_time=time(23, 0), days: int = 1
):
    """计划任务 - 启动相关站点的一次持续观看."""

    timestamp_file = Path(config["basedir"]) / "watcher_continuous_schedule_next_timestamp"
    current_config = {
        "start_time": start_time.strftime("%H:%M"),
        "end_time": end_time.strftime("%H:%M"),
        "days": days,
    }

    while True:
        next_dt = None
        config_changed = False

        if timestamp_file.exists():
            try:
                stored_data = json.loads(timestamp_file.read_text())
                if not isinstance(stored_data, dict):
                    raise ValueError("invalid cache")
                stored_timestamp = stored_data["timestamp"]
                stored_config = stored_data["config"]

                if stored_config != current_config:
                    logger.bind(scheme="embywatcher").info("计划任务配置已更改，将重新计算下次执行时间.")
                    config_changed = True
                else:
                    next_dt = datetime.fromtimestamp(stored_timestamp)
                    if next_dt > datetime.now():
                        logger.bind(scheme="embywatcher").info(
                            f"从缓存中读取到下次持续观看时间: {next_dt.strftime('%m-%d %H:%M %p')}."
                        )
            except (ValueError, OSError, json.JSONDecodeError) as e:
                logger.debug(f"读取存储的时间戳失败: {e}")
                config_changed = True

        if not next_dt or next_dt <= datetime.now() or config_changed:
            next_dt = next_random_datetime(start_time, end_time, interval_days=days)
            logger.bind(scheme="embywatcher").info(
                f"下次持续观看将在 {next_dt.strftime('%m-%d %H:%M %p')} 开始."
            )
            try:
                save_data = {"timestamp": next_dt.timestamp(), "config": current_config}
                timestamp_file.write_text(json.dumps(save_data))
            except OSError as e:
                logger.debug(f"存储时间戳失败: {e}")

        await asyncio.sleep((next_dt - datetime.now()).total_seconds())
        try:
            timestamp_file.unlink(missing_ok=True)
        except OSError as e:
            logger.debug(f"删除时间戳文件失败: {e}")
        t = asyncio.create_task(watcher_continuous(config))
        if not t.done():
            t.cancel()


async def play_url(config: dict, url: str):
    """播放指定URL的视频"""
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(url)

    fragment_parts = parsed.fragment.split("?", 1)
    if len(fragment_parts) > 1:
        params = parse_qs(fragment_parts[1])
    else:
        params = {}

    if not params.get("id"):
        logger.error(
            "无效的 URL 格式, 无法解析视频 ID. 应为类似:\nhttps://example.com/web/#/details?id=xxx&serverId=xxx"
        )
        return False

    video_id = params["id"][0]

    # 在config中查找匹配的emby配置
    matched_config = None
    for emby_config in config.get("emby", []):
        emby_url = emby_config.get("url", "").rstrip("/")
        if urlparse(emby_url).netloc == parsed.netloc:
            matched_config = emby_config
            break

    if not matched_config:
        logger.error(f"在配置中未找到匹配的 Emby 服务器: {parsed.netloc}")
        return False

    filtered_config = config.copy()
    filtered_config["emby"] = [matched_config]

    async for emby, loggeruser, _, _, _, _ in login(filtered_config):
        logger.info(f'已登陆到 Emby: {matched_config["url"]}')
        connector: Connector = emby.connector
        logger.info("使用以下 Headers:")
        for k, v in connector.headers.items():
            logger.info(f"\t{k}: {v}")
        item = await emby.get_item(video_id)
        if not item:
            raise ValueError(f"无法找到 ID 为 {video_id} 的视频")
        loggeruser.info(f'10 秒后, 将开始播放该视频 300 秒: "{truncate_str(item.name, 10)}"')
        await asyncio.sleep(30)
        loggeruser.info(f'开始播放视频 300 秒: "{truncate_str(item.name, 10)}"')
        await play(item, loggeruser, time=300)
    return True
