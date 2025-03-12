import asyncio
from datetime import datetime
import random
import string
from urllib.parse import quote
import uuid
from typing import Iterable, List, Union, Optional
import re

from loguru import logger
from curl_cffi.requests import AsyncSession, Response, RequestsError
from pydantic import BaseModel, ValidationError

from embykeeper import __version__
from embykeeper.utils import get_proxy_str, show_exception, truncate_str
from embykeeper.cache import cache
from embykeeper.schema import EmbyAccount
from embykeeper.config import config

logger = logger.bind(scheme="embywatcher")


class EmbyError(Exception):
    pass


class EmbyRequestError(EmbyError):
    pass


class EmbyConnectError(EmbyError):
    pass


class EmbyLoginError(EmbyRequestError):
    pass


class EmbyStatusError(EmbyRequestError):
    pass


class EmbyPlayError(EmbyError):
    pass


class EmbyEnv(BaseModel):
    client: str
    device: str
    device_id: str
    client_version: str
    useragent: str


class Emby:
    playing_count = 0

    def __init__(self, account: EmbyAccount):
        self.a = account

        self._env = None
        self._token = None
        self._user_id = None

        self.run_id = str(uuid.uuid4()).upper()
        self.cf_clearance = None
        self.useragent = None
        self.items = {}

        self.log = logger.bind(server=self.a.name or self.hostname, username=self.a.username)

    @property
    def proxy(self):
        return config.proxy if self.a.use_proxy else None

    @property
    def hostname(self):
        return self.a.url.host

    @property
    def token(self):
        if not self._token:
            self._load_credentials()
        return self._token

    @property
    def env(self):
        if not self._env:
            self._load_env()
        if not self._env:
            self._env = self.get_fake_env()
        return self._env

    @property
    def user_id(self):
        if not self._user_id:
            self._load_credentials()
        return self._user_id

    def _load_credentials(self):
        data: dict = cache.get(f"emby.credential.{self.hostname}.{self.a.username}", {})
        self._token = data.get("token", None)
        self._user_id = data.get("userid", None)

    def _load_env(self):
        cache_key = f"emby.env.{self.hostname}.{self.a.username}"
        data: dict = cache.get(cache_key, {})
        if data:
            # 检查用户配置是否与缓存一致
            should_clear = False
            for key, user_value in {
                "client_version": self.a.client_version,
                "client": self.a.client,
                "device": self.a.device,
                "device_id": self.a.device_id,
                "useragent": self.a.useragent,
            }.items():
                if user_value and data.get(key) != user_value:
                    should_clear = True
                    break

            if should_clear:
                logger.info("账户设置已修改, 将重新生成环境 (Headers).")
                self._env = None
                cache.delete(cache_key)
            else:
                try:
                    self._env = EmbyEnv.model_validate(data)
                except ValidationError:
                    logger.warning("缓存加载失败, 将重新生成环境 (Headers).")
                    self._env = None

    @staticmethod
    def get_random_device():
        from faker import Faker

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

    @staticmethod
    def get_device_uuid():
        rd = random.Random()
        rd.seed(uuid.getnode())
        return uuid.UUID(int=rd.getrandbits(128))

    def get_fake_env(self):
        cached_env: dict = cache.get(f"emby.env.{self.hostname}.{self.a.username}", {})

        # 按优先级获取各个值
        is_filebar = random.random() < 0.2
        version = (
            self.a.client_version
            or cached_env.get("client_version")
            or f"1.3.{random.randint(34, 34) if is_filebar else random.randint(16, 30)}"
        )
        client = self.a.client or cached_env.get("client") or ("Filebar" if is_filebar else "Fileball")
        device = self.a.device or cached_env.get("device") or self.get_random_device()
        device_id = self.a.device_id or cached_env.get("device_id") or str(uuid.uuid4()).upper()
        useragent = self.useragent or self.a.useragent or cached_env.get("ua") or f"{client}/{version}"

        data = {
            "client": client,
            "device": device,
            "device_id": device_id,
            "client_version": version,
            "useragent": useragent,
        }

        env = EmbyEnv(**data)
        cache.set(f"emby.env.{self.hostname}.{self.a.username}", data)
        return env

    def build_headers(self):
        headers = {}
        auth_headers = {
            "Client": self.env.client,
            "Device": self.env.device,
            "DeviceId": self.env.device_id,
            "Version": self.env.client_version,
        }
        auth_header = ",".join([f"{k}={quote(str(v))}" for k, v in auth_headers.items()])
        full_auth_header = f'MediaBrowser Token={self.token or ""},Emby UserId={self.run_id},{auth_header}'
        headers["User-Agent"] = self.useragent or self.env.useragent
        headers["Accept-Language"] = "zh-CN,zh-Hans;q=0.9"
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "*/*"
        headers["X-Emby-Authorization"] = full_auth_header
        if self.token:
            headers["X-Emby-Token"] = self.token
        return headers

    def _get_session(self) -> AsyncSession:
        cookies = {}
        if self.cf_clearance:
            cookies["cf_clearance"] = self.cf_clearance

        return AsyncSession(
            verify=False,
            headers=self.build_headers(),
            cookies=cookies,
            proxy=get_proxy_str(self.proxy),
            timeout=10.0,
            impersonate="chrome",
            allow_redirects=True,
            default_headers=False,
        )

    async def _request(self, method: str, path: str, _login=False, **kw) -> Response:

        if path.startswith(("http://", "https://")):
            url = path
        else:
            base_url = f"{self.a.url.scheme}://{self.a.url.host}:{self.a.url.port}"
            url = f"{base_url}/{path.lstrip('/')}"

        last_err = None
        for _ in range(3):
            try:
                async with self._get_session() as session:
                    resp: Response = await session.request(method, url, **kw)
                    if resp.status_code == 401 and self.a.username and not _login:
                        if not await self.login():
                            raise EmbyLoginError("无法登陆到服务器")
                        continue
                    elif resp.status_code in (502, 503, 504):
                        await asyncio.sleep(random.random() * 2 + 0.5)
                        continue
                    elif resp.status_code == 403 and (
                        "cf-wrapper" in resp.text or "Just a moment" in resp.text
                    ):
                        if self.cf_clearance:
                            raise EmbyStatusError("访问失败: Cloudflare 验证码解析后依然有验证")
                        await self.use_cfsolver()
                        continue
                    elif not resp.ok and not _login:
                        raise EmbyStatusError(f"访问失败: 异常 HTTP 代码 {resp.status_code} (URL = {url})")
                    else:
                        return resp
            except RequestsError as e:
                last_err = e
                await asyncio.sleep(random.random() + 0.5)

        error_msg = re.sub(r"\s+See\s+.*?\s+first for more details\.\.?", "", str(last_err))
        raise EmbyConnectError(f"{last_err.__class__.__name__}: {error_msg}")

    async def use_cfsolver(self):
        from embykeeper.cloudflare import get_cf_clearance

        if not self.a.cf_challenge:
            if self.proxy:
                self.log.warning(
                    f"该站点已启用 Cloudflare 保护, 请尝试浏览器以同样的代理访问: {self.a.url}"
                    "以解除 Cloudflare IP 限制, 然后再次运行.\n"
                    '或者, 高级用户可以使用 "cf_challenge = true" 配置项以允许尝试解析验证码.'
                )
            else:
                self.log.warning(
                    f'该站点已启用 Cloudflare 保护, 请使用 "cf_challenge = true" 配置项以允许尝试解析验证码.'
                )
        self.log.info(f"该站点已启用 Cloudflare 保护, 即将请求解析.")
        if self.proxy:
            if self.proxy.scheme != "socks5":
                self.log.warning(
                    f"该站点验证解析仅支持 SOCKS5 代理，由于当前代理协议不支持, 将尝试不使用代理."
                )
                self.a.use_proxy = False
            else:
                self.log.info(
                    f"验证码解析将使用代理, 可能导致解析失败, 若失败请使用"
                    '"use_proxy = false" 以禁用该站点的代理.'
                )
        try:
            cf_clearance, useragent = await get_cf_clearance(self.a.url, self.proxy)
            if not cf_clearance:
                self.log.warning(f"Cloudflare 验证码解析失败.")
                return False
            else:
                self.cf_clearance = cf_clearance
                self.useragent = useragent
                return True
        except Exception as e:
            self.log.warning(f"Cloudflare 验证码解析时出现错误.")
            show_exception(e, regular=False)
            return False

    async def login(self) -> dict:
        """Login to Emby server and get authentication token."""

        if self.a.username is None or self.a.password is None:
            self.log.warning("没有提供用户名或密码, 无法登陆, 执行失败.")
            return None

        data = {
            "Username": self.a.username,
            "Pw": self.a.password,
        }

        resp = await self._request(
            "POST",
            "/Users/AuthenticateByName",
            json=data,
            _login=True,
        )

        if resp.status_code == 401:
            self.log.warning(f"用户名或密码错误, 执行失败.")
            return None

        if resp.status_code != 200:
            self.log.warning(f"登陆时出现错误 ({resp.status_code}), 执行失败.")
            return None

        user: dict = resp.json()
        self._token = user.get("AccessToken", None)
        self._user_id = user.get("User", {}).get("Id")
        if self.token and self.user_id:
            cache_data = {
                "token": self.token,
                "userid": self.user_id,
            }
            cache.set(f"emby.credential.{self.hostname}.{self.a.username}", cache_data)
            return self.token

    async def play(self, item: Union[dict, int], time: float = 10):
        if isinstance(item, dict):
            try:
                iid = item["Id"]
                iname = item["Name"]
            except KeyError:
                raise EmbyPlayError("无法解析视频信息")
        else:
            iid = item
            iname = "(请求播放的视频)"

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

        resp = await self._request(
            method="GET",
            path=f"/Videos/{iid}/AdditionalParts",
            params=dict(
                Fields="PrimaryImageAspectRatio,UserData,CanDelete",
                IncludeItemTypes="Playlist,BoxSet",
                Recursive=True,
                SortBy="SortName",
            ),
        )

        resp = await self._request(
            method="POST",
            path=f"/Items/{iid}/PlaybackInfo",
            params=dict(
                AutoOpenLiveStream=False,
                IsPlayback=False,
                MaxStreamingBitrate=40000000,
                StartTimeTicks=0,
                UserID=self.user_id,
            ),
            json=playback_info_data,
        )
        playback_info = resp.json()

        play_session_id = playback_info.get("PlaySessionId", "")
        if "MediaSources" in playback_info:
            media_source_id = playback_info["MediaSources"][0]["Id"]
            direct_stream_url = playback_info["MediaSources"][0].get("DirectStreamUrl", None)
        else:
            media_source_id = "".join(
                random.choice(string.ascii_lowercase + string.digits) for _ in range(32)
            )
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

            resp = await self._request(
                method="POST",
                path=f"/Items/{iid}/PlaybackInfo",
                params=dict(
                    AudioStreamIndex=1,
                    AutoOpenLiveStream=AutoOpenLiveStream,
                    IsPlayback=IsPlayback,
                    MaxStreamingBitrate=42000000,
                    MediaSourceId=str(media_source_id),
                    StartTimeTicks=0,
                    UserID=self.user_id,
                ),
                json=playback_info_data,
            )

        def get_playing_data(tick, update=False, stop=False):
            data = {
                "SubtitleOffset": 0,
                "MaxStreamingBitrate": 420000000,
                "MediaSourceId": str(media_source_id),
                "SubtitleStreamIndex": -1,
                "VolumeLevel": 100,
                "PlaybackRate": 1,
                "PlaybackStartTimeTicks": int(datetime.now().timestamp() // 10 * 10 * 10000000),
                "PositionTicks": tick,
                "PlaySessionId": play_session_id,
            }
            if update:
                data["EventName"] = "timeupdate"
            if stop:
                queue = []
            else:
                queue = [{"Id": str(iid), "PlaylistItemId": "playlistItem0"}]
            data.update(
                {
                    "PlaylistLength": 1,
                    "NowPlayingQueue": queue,
                    "IsMuted": False,
                    "PlaylistIndex": 0,
                    "ItemId": str(iid),
                    "RepeatMode": "RepeatNone",
                    "AudioStreamIndex": -1,
                    "PlayMethod": "DirectStream",
                    "CanSeek": True,
                    "IsPaused": False,
                }
            )
            return data

        async def stream():
            url = direct_stream_url or f"/Videos/{iid}/stream"
            length = 0
            last_err_time = datetime.now()
            while True:
                resp = await self._request(
                    method="GET",
                    path=url,
                    stream=True,
                    max_recv_speed=1024,
                    timeout=None,
                    headers={
                        "Range": f"bytes={length}-",
                        "User-Agent": "VLC/3.0.21 LibVLC/3.0.21",
                        "X-Playback-Session-Id": play_session_id,
                    },
                )
                try:
                    async for i in resp.aiter_content(chunk_size=1024):
                        length += len(i)
                        del i
                        await asyncio.sleep(random.random())
                        if random.random() < 0.01:
                            continue
                except RequestsError:
                    if (datetime.now() - last_err_time).total_seconds() > 5:
                        self.log.debug("流媒体文件访问错误, 正在重试.")
                        last_err_time = datetime.now()
                        continue
                    else:
                        raise
                finally:
                    await resp.aclose()

        stream_task = asyncio.create_task(stream())
        rt = random.uniform(5, 10)
        self.log.info(f'开始模拟加载视频 "{truncate_str(iname, 10)}" ({rt:.0f} 秒).')
        await asyncio.sleep(rt)
        self.log.info(f'开始发送视频 "{truncate_str(iname, 10)}" 发送进度.')
        Emby.playing_count += 1
        try:
            await asyncio.sleep(random.uniform(1, 3))
            try:
                resp = await self._request(
                    method="POST",
                    path="/Sessions/Playing",
                    json=get_playing_data(0),
                )
            except EmbyRequestError as e:
                raise EmbyPlayError(f"无法开始播放: {e}")
            t = time

            last_report_t = t
            progress_errors = 0
            report_interval = 5  # Start with 5 seconds
            report_count = 0
            max_interval = 300  # 5 minutes in seconds
            while t > 0:
                if progress_errors > 12:
                    raise EmbyPlayError("播放状态设定错误次数过多")
                if last_report_t and last_report_t - t > report_interval:
                    self.log.info(f'正在播放: "{truncate_str(iname, 10)}" (还剩 {t:.0f} 秒).')
                    last_report_t = t
                    report_count += 1
                    # After 3 reports at current interval, double the interval
                    if report_count >= 3:
                        report_count = 0
                        report_interval = min(report_interval * 2, max_interval)
                st = min(10, t)
                await asyncio.sleep(st)
                t -= st
                tick = int((time - t) * 10000000)
                payload = get_playing_data(tick, update=True)
                try:
                    resp = await asyncio.wait_for(
                        self._request(
                            method="POST",
                            path="/Sessions/Playing/Progress",
                            json=payload,
                        ),
                        10,
                    )
                except Exception as e:
                    self.log.debug(f"播放状态设定错误: {e}")
                    progress_errors += 1
            await asyncio.sleep(random.uniform(1, 3))
        finally:
            Emby.playing_count -= 1
            stream_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self.log.warning(f"模拟播放时, 访问流媒体文件失败.")
                show_exception(e)

        try:
            final_percentage = random.uniform(0.95, 1.0)
            final_tick = int((time * final_percentage) // 10 * 10 * 10000000)
            await self._request(
                method="POST",
                path="/Sessions/Playing/Progress",
                json=get_playing_data(final_tick, stop=True),
            )
            self.log.info(f"播放完成, 共 {time:.0f} 秒.")
            return True
        except Exception as e:
            raise EmbyPlayError(f"由于连接错误或服务器错误无法停止播放: {e}")

    async def load_main_page(self):
        views = await self._request(
            method="GET",
            path=f"/Users/{self.user_id}/Views",
            params=dict(IncludeExternalContent=False),
        )

        col_ids = []
        for i in views.json().get("Items", []):
            cid: str = i.get("Id", None)
            type: str = i.get("CollectionType")
            if cid and type and type.lower() in ("movies", "tvshows"):
                col_ids.append(cid)
        await asyncio.sleep(random.uniform(0.1, 0.3))

        user = await self._request(method="GET", path=f"/Users/{self.user_id}")
        last_login_date = user.json().get("LastLoginDate", None)
        await asyncio.sleep(random.uniform(0.1, 0.3))

        await self._request(
            method="GET",
            path=f"/DisplayPreferences/usersettings",
            params=dict(client="emby", userId=self.user_id),
        )
        await asyncio.sleep(random.uniform(0.1, 0.3))

        await self.get_resume_items(media_types=["Video"])
        await asyncio.sleep(random.uniform(0.1, 0.3))
        await self.get_resume_items(media_types=["Audio"])
        await asyncio.sleep(random.uniform(0.1, 0.3))

        for cid in col_ids[:25]:
            items = await self.get_latest_items(parent_id=cid)
            for item in items:
                try:
                    iid = item["Id"]
                    self.items[iid] = item
                except KeyError:
                    pass

        if not self.items:
            if col_ids:
                self.log.info("无法获取最新视频, 尝试从文件夹中读取.")

                for col_id in col_ids[:3]:
                    await asyncio.sleep(4)
                    items = await self.get_folder_items(parent_id=col_id)
                    for item in items:
                        try:
                            iid = item["Id"]
                            self.items[iid] = item
                        except KeyError:
                            pass
                    if len(self.items) >= 3:
                        break

        return last_login_date

    async def get_latest_items(
        self,
        enable_image_types=None,
        fields=None,
        limit=16,
        group_items=True,
        parent_id=None,
        **kw,
    ) -> List[dict]:
        if not enable_image_types:
            enable_image_types = ["Primary", "Backdrop", "Thumb"]
        if not fields:
            fields = [
                "PrimaryImageAspectRatio",
                "BasicSyncInfo",
                "ProductionYear",
                "Status",
                "EndDate",
                "CanDelete",
            ]
        resp = await self._request(
            method="GET",
            path=f"/Users/{self.user_id}/Items/Latest",
            params={
                "EnableImageTypes": ",".join(enable_image_types),
                "Fields": ",".join(fields),
                "GroupItems": group_items,
                "Limit": limit,
                "ParentId": parent_id,
                **kw,
            },
        )
        return resp.json()

    async def get_resume_items(
        self,
        enable_image_types=None,
        fields=None,
        limit=12,
        media_types=None,
        **kw,
    ) -> List[dict]:
        if not enable_image_types:
            enable_image_types = ["Primary", "Backdrop", "Thumb"]
        if not fields:
            fields = ["PrimaryImageAspectRatio", "BasicSyncInfo", "ProductionYear", "CanDelete"]
        if not media_types:
            media_types = ["Video"]
        resp = await self._request(
            method="GET",
            path=f"/Users/{self.user_id}/Items/Resume",
            params={
                "EnableImageTypes": ",".join(enable_image_types),
                "Fields": ",".join(fields),
                "Limit": limit,
                "MediaTypes": ",".join(media_types),
                "Recursive": "true",
                **kw,
            },
        )
        return resp.json()

    async def get_folder_items(
        self,
        parent_id,
        enable_image_types=None,
        fields=None,
        limit=50,
        **kw,
    ) -> List[dict]:
        if not enable_image_types:
            enable_image_types = ["Primary", "Backdrop", "Thumb"]
        if not fields:
            fields = ["BasicSyncInfo", "CanDelete", "PrimaryImageAspectRatio", "ProductionYear"]
        resp = await self._request(
            method="GET",
            path=f"/Users/{self.user_id}/Items",
            params={
                "EnableImageTypes": ",".join(enable_image_types),
                "Fields": ",".join(fields),
                "ImageTypeLimit": 1,
                "IncludeItemTypes": "Movie",
                "Limit": limit,
                "ParentId": parent_id,
                "Recursive": "true",
                "SortBy": "SortName",
                "SortOrder": "Ascending",
                "StartIndex": 0,
                **kw,
            },
        )
        return resp.json().get("Items", [])

    async def get_item(self, iid, **kw) -> dict:
        resp = await self._request(method="GET", path=f"/Users/{self.user_id}/Items/{iid}")
        return resp.json()

    async def get_user(self) -> dict:
        """Get current user information."""
        response = await self._request("GET", f"/Users/{self.user_id}")
        return response.json()

    async def mark_played(self, item_id: str) -> bool:
        """Mark an item as played."""
        response = await self._request("POST", f"/Users/{self.user_id}/PlayedItems/{item_id}")
        return response.status_code == 200

    async def watch(self):
        """Play one or more videos until account time requirement played."""

        if self.a.continuous:
            self.log.info("开始连续播放视频")
        else:
            try:
                if isinstance(self.a.time, Iterable):
                    req_time = random.uniform(*self.a.time)
                else:
                    req_time = self.a.time
            except TypeError:
                self.log.warning(
                    f"无法解析 time 配置, 请检查配置: {self.a.time} (应该为数字或两个数字的数组)."
                )
                return False
            msg = " (允许播放多个)" if self.a.allow_multiple else ""
            msg = f"开始播放视频{msg}, 共需播放 {req_time:.0f} 秒."
            self.log.info(msg)

        played_time = 0
        last_played_time = 0
        played_videos = 0
        retry = 0
        failed_items = []
        failed_reasons = {"invalid": 0, "no_length": 0, "wrong_type": 0, "short_length": 0}

        while True:
            shuffled_items = list(self.items.items())
            random.shuffle(shuffled_items)

            for iid, item in shuffled_items:
                try:
                    if iid in failed_items:
                        failed_reasons["invalid"] += 1
                        continue
                except KeyError:
                    continue
                media_type = item.get("MediaType", None)
                if not media_type == "Video":
                    failed_reasons["wrong_type"] += 1
                    continue
                total_ticks = item.get("RunTimeTicks", None)
                if not total_ticks:
                    if self.a.allow_stream:
                        total_ticks = min(req_time, random.randint(480, 720)) * 10000000
                    else:
                        failed_reasons["no_length"] += 1
                        continue
                total_time = total_ticks / 10000000
                if req_time - played_time > total_time:
                    if (not self.a.allow_multiple) and (not self.a.continuous):
                        failed_reasons["short_length"] += 1
                        failed_items.append(iid)
                        continue
                    play_time = total_time
                else:
                    play_time = max(req_time - played_time, 10)
                name = truncate_str(item.get("Name", "(未命名视频)"), 10)
                self.log.info(f'开始播放 "{name}" ({play_time:.0f} 秒).')
                while True:
                    try:
                        await self.play(item, time=play_time)
                        await asyncio.sleep(random.random())
                        item = await self.get_item(iid)
                        play_count = item.get("UserData", {}).get("PlayCount", 0)
                        if play_count < 1:
                            raise EmbyPlayError("播放后播放数低于 1")
                        self.log.info(f"[yellow]成功播放视频[/], 当前该视频播放 {play_count} 次.")
                        played_videos += 1
                        played_time += play_time
                        if played_time >= req_time - 1:
                            self.log.bind(log=True).info(f"保活成功, 共播放 {played_videos} 个视频.")
                            return True
                        else:
                            self.log.info(f"还需播放 {req_time - played_time:.0f} 秒.")
                            rt = random.uniform(5, 15)
                            self.log.info(f"等待 {rt:.0f} 秒后播放下一个.")
                            await asyncio.sleep(rt)
                            break
                    except EmbyError as e:
                        retry += 1
                        if retry > config.emby.retries:
                            self.log.warning(f"超过最大重试次数, 保活失败: {e}.")
                            return False
                        else:
                            rt = random.uniform(30, 60)
                            if isinstance(e, EmbyPlayError):
                                self.log.info(f"播放错误, 等待 {rt:.0f} 秒后重试: {e}.")
                            else:
                                self.log.info(f"连接失败, 等待 {rt:.0f} 秒后重试: {e}.")
                            await asyncio.sleep(rt)
                    except Exception as e:
                        self.log.warning(f"发生错误, 保活失败.")
                        show_exception(e, regular=False)
                        return False
            else:
                if len(failed_items) == len(self.items):
                    reasons = []
                    if failed_reasons["invalid"]:
                        reasons.append(f"{failed_reasons['invalid']} 个视频信息无效")
                    if failed_reasons["no_length"]:
                        reasons.append(f"{failed_reasons['no_length']} 个视频无法获取时长")
                    if failed_reasons["wrong_type"]:
                        reasons.append(f"{failed_reasons['wrong_type']} 个非视频项目")
                    if failed_reasons["short_length"]:
                        reasons.append(
                            f"{failed_reasons['short_length']} 个视频时长不足 (未开启 allow_multiple)"
                        )
                    self.log.warning(f"所有视频均不符合要求, 保活失败. 其中: {', '.join(reasons)}")
                elif played_time > last_played_time:
                    last_played_time = played_time
                    continue
                else:
                    self.log.warning(f"由于没有成功播放视频, 保活失败, 请重新检查配置.")
                    return False

    @staticmethod
    def parse_date(date_str: str) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None
