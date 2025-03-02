import asyncio
from dataclasses import dataclass
import hashlib
import re
import time
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin
import random

from curl_cffi.requests import AsyncSession, RequestsError, Response
from loguru import logger

from embykeeper.utils import get_proxy_str

logger = logger.bind(scheme="subsonic")


class SubsonicError(Exception):
    pass


class SubsonicRequestError(SubsonicError):
    pass


class SubsonicConnectError(SubsonicError):
    pass


class SubsonicLoginError(SubsonicRequestError):
    pass


class SubsonicStatusError(SubsonicRequestError):
    pass


class SubsonicPlayError(SubsonicError):
    pass


@dataclass
class ServerPingInfo:
    is_ok: bool = True
    type: str = None
    version: str = None
    server_version: str = None
    open_subsonic: bool = True
    error_code: int = None
    error_message: str = None


class Subsonic:
    """
    An async client for interacting with Subsonic API.
    """

    def __init__(
        self,
        server: str,
        username: str,
        password: str,
        proxy: Optional[Dict] = None,
        useragent: Optional[str] = None,
        client: Optional[str] = None,
        version: Optional[str] = None,
    ):
        self.server = server
        self.username = username
        self.password = password
        self.proxy = proxy
        self.salt = self._generate_salt()
        self.token = self._generate_token()
        self.version = version or "1.15.0"
        self.client = client or "Stream Music"
        self.useragent = useragent or "Dart/3.4 (dart:io)"

        self._session = None
        self._session_lock = asyncio.Lock()

    def _generate_salt(self, length: int = 6) -> str:
        """Generate a random salt for authentication"""
        return hashlib.md5(str(time.time()).encode()).hexdigest()[:length]

    def _generate_token(self) -> str:
        """Generate authentication token using password and salt"""
        return hashlib.md5(f"{self.password}{self.salt}".encode()).hexdigest()

    async def _get_session(self) -> AsyncSession:
        """Get or create an HTTP session"""
        async with self._session_lock:
            if not self._session or self._session._closed:
                headers = {"User-Agent": self.useragent}
                self._session = AsyncSession(
                    verify=False,
                    timeout=10.0,
                    proxy=get_proxy_str(self.proxy),
                    headers=headers,
                    impersonate="chrome",
                    allow_redirects=True,
                    default_headers=False,
                )
            return self._session

    async def _request(self, path: str, params: Optional[Dict[str, Any]] = None) -> dict:
        """
        Make an async API request to Subsonic server
        """
        base_params = {
            "u": self.username,
            "t": self.token,
            "s": self.salt,
            "c": self.client,
            "v": self.version,
            "f": "json",
        }

        if params:
            base_params.update(params)

        url = urljoin(self.server, f"rest/{path}")

        last_err = None
        for _ in range(3):
            try:
                session = await self._get_session()
                response: Response = await session.get(url, params=base_params)
                if response.status_code == 401:
                    raise SubsonicLoginError("用户名密码错误或无权访问")
                response.raise_for_status()
                try:
                    return response.json()["subsonic-response"]
                except KeyError:
                    raise SubsonicStatusError("不是有效的 Subsonic 服务器")
            except RequestsError as e:
                last_err = e
                await asyncio.sleep(random.random() + 0.5)

        error_msg = re.sub(r"\s+See\s+.*?\s+first for more details\.\.?", "", str(last_err))
        raise SubsonicConnectError(f"{last_err.__class__.__name__}: {error_msg}")

    async def ping(self):
        """Test connection to server"""
        try:
            response = await self._request("ping")
            if response.get("status", None) == "ok":
                return ServerPingInfo(
                    type=response.get("type", None),
                    version=response.get("version", None),
                    server_version=response.get("serverVersion", None),
                    open_subsonic=response.get("openSubsonic", None),
                )
            else:
                return ServerPingInfo(
                    is_ok=False,
                    error_code=response.get("error", {}).get("code", None),
                    error_message=response.get("error", {}).get("message", None),
                )
        except Exception as e:
            return ServerPingInfo(
                is_ok=False, error_message=f"Client error occurs: {e.__class__.__name__}: {e}"
            )

    async def get_music_folders(self) -> List[Dict]:
        """Get all music folders"""
        response = await self._request("getMusicFolders")
        return response.get("musicFolders", {}).get("musicFolder", [])

    async def get_artists(self, folder_id: Optional[str] = None) -> List[Dict]:
        """Get all artists in a music folder"""
        params = {"musicFolderId": folder_id} if folder_id else {}
        response = await self._request("getArtists", params)
        return response.get("artists", {}).get("index", [])

    async def get_artist(self, artist_id: str) -> Dict:
        """Get artist details"""
        response = await self._request("getArtist", {"id": artist_id})
        return response.get("artist", {})

    async def get_album(self, album_id: str) -> Dict:
        """Get album details"""
        response = await self._request("getAlbum", {"id": album_id})
        return response.get("album", {})

    async def get_song(self, song_id: str) -> Dict:
        """Get song details"""
        response = await self._request("getSong", {"id": song_id})
        return response.get("song", {})

    async def get_random_songs(
        self, size: int = 1, genre: Optional[str] = None, folder_id: Optional[str] = None
    ) -> List[Dict]:
        """Get random songs from the server"""
        params = {"size": size}
        if genre:
            params["genre"] = genre
        if folder_id:
            params["musicFolderId"] = folder_id

        response = await self._request("getRandomSongs", params)
        return response.get("randomSongs", {}).get("song", [])

    async def scrobble(self, song_id: str, submission: bool = True, time: Optional[int] = None) -> None:
        """
        Submit listening data to the server
        submission=True: The song was played fully
        submission=False: The song just started playing
        """
        params = {"id": song_id, "submission": "true" if submission else "false"}
        if time:
            params["time"] = time

        await self._request("scrobble", params)

    async def close(self):
        """Close the client and cleanup resources"""
        if self._session:
            await self._session.close()

    async def stream_noreturn(self, song_id: str) -> None:
        """Stream a song very slowly to simulate playback"""
        try:
            params = {
                "u": self.username,
                "t": self.token,
                "s": self.salt,
                "c": self.client,
                "v": self.version,
                "id": song_id,
            }
            url = urljoin(self.server, "rest/stream")

            session = await self._get_session()
            resp: Response = await session.get(
                url,
                params=params,
                timeout=None,
                max_recv_speed=1024,
                stream=True,
            )
            try:
                resp.raise_for_status()
                async for _ in resp.aiter_content(chunk_size=1024):
                    await asyncio.sleep(random.random())
            finally:
                resp.close()
        except asyncio.CancelledError:
            pass
