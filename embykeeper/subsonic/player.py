import asyncio
import random
from typing import Iterable
from loguru import logger

from embykeeper.config import config
from embykeeper.schema import SubsonicAccount
from embykeeper.utils import show_exception

from .api import Subsonic, SubsonicConnectError, SubsonicRequestError

logger = logger.bind(scheme="subsonic")


class SubsonicPlayer:
    def __init__(self, account: SubsonicAccount):
        self.a = account
        self.cf_clearance = None
        self.useragent = None

        self.log = logger.bind(server=self.a.name or self.hostname, username=self.a.username)

    @property
    def proxy(self):
        return config.proxy if self.a.use_proxy else None

    @property
    def hostname(self):
        return self.a.url.host

    async def login(self):
        """登录账号."""
        client = Subsonic(
            server=str(self.a.url),
            username=self.a.username,
            password=self.a.password,
            proxy=self.proxy,
            useragent=self.useragent,
            client=self.a.client,
            version=self.a.client_version,
        )
        try:
            info = await client.ping()
            if info.is_ok:
                self.log.info(
                    f'成功连接至服务器 ({(info.type or "unknown").capitalize()} {info.version or "X.X"}).'
                )
                return client
            else:
                self.log.error(f"服务器登陆错误, 请重新检查配置: {info.error_message}")
                return None
        except SubsonicConnectError as e:
            self.log.warning(f"服务器登陆错误, 无法连接: {e}")
            return None
        except SubsonicRequestError as e:
            self.log.warning(f"服务器登陆错误, 服务器异常: {e}")
            return None

    async def play(self, client: Subsonic):
        """模拟连续播放音频直到达到指定总时长."""

        try:
            if isinstance(self.a.time, Iterable):
                req_time = random.uniform(*self.a.time)
            else:
                req_time = self.a.time
        except TypeError:
            self.log.warning(f"无法解析 time 配置, 请检查配置: {self.a.time} (应该为数字或两个数字的数组).")
            return False

        played_time = 0
        retry = 0

        while played_time < req_time:
            try:
                songs = await client.get_random_songs()
                if not songs:
                    self.log.warning("未能获取到任何歌曲.")
                    return False
                song = random.choice(songs)
                song_id = song.get("id", None)
                if not song_id:
                    self.log.warning("获取到歌曲信息不完整, 正在重试.")
                    continue

                song_title = song.get("title", "未知歌曲")
                song_duration = float(song.get("duration", 60))
                remaining_time = req_time - played_time

                play_duration = min(remaining_time, song_duration) if song_duration > 0 else remaining_time

                self.log.info(f'开始播放 "{song_title}", 剩余时间 {remaining_time:.0f} 秒.')
                while retry < config.subsonic.retries:
                    try:
                        await client.scrobble(song_id, submission=False)
                        await asyncio.wait_for(client.stream_noreturn(song_id), timeout=play_duration)
                        played_time += play_duration
                        await client.scrobble(song_id, submission=True)
                        self.log.info(f'完成播放 "{song_title}", 已播放 {played_time:.0f} 秒.')
                        retry = 0
                        break
                    except asyncio.TimeoutError:
                        # 正常超时，说明歌曲播放完成
                        played_time += play_duration
                        await client.scrobble(song_id, submission=True)
                        self.log.info(f'完成播放 "{song_title}", 已播放 {played_time:.0f} 秒.')
                        break
                    except Exception as e:
                        retry += 1
                        if retry >= config.subsonic.retries:
                            self.log.error(f"播放出错且达到最大重试次数, 停止播放.")
                            show_exception(e, regular=False)
                            return False
                        self.log.warning(f"播放出错 (重试 {retry}/{config.subsonic.retries}), 正在重试.")
                        show_exception(e, regular=False)
                        await asyncio.sleep(1)
                        continue
            except Exception as e:
                retry += 1
                if retry >= config.subsonic.retries:
                    self.log.error(f"播放出错且达到最大重试次数, 停止播放.")
                    show_exception(e, regular=False)
                    return False
                self.log.warning(f"访问出错 (重试 {retry}/{config.subsonic.retries}), 正在重试: {e}.")
                show_exception(e, regular=True)
                await asyncio.sleep(1)
                continue
        return True
