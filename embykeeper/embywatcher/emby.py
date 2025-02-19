import asyncio
import json
from pathlib import Path
import random
from urllib.parse import urlencode, urlunparse
import uuid
import warnings

import httpx
from loguru import logger

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from embypy.emby import Emby as _Emby
    from embypy.objects import EmbyObject
    from embypy.utils.asyncio import async_func
    from embypy.utils.connector import Connector as _Connector

from embykeeper.utils import get_proxy_str

from .. import __version__

logger = logger.bind(scheme="embywatcher")


class Connector(_Connector):
    """重写的 Emby 连接器, 以支持代理."""

    playing_count = 0
    cache_lock = asyncio.Lock()

    def __init__(
        self,
        url,
        headers,
        proxy=None,
        basedir=None,
        auth_header=None,
        cf_clearance=None,
        **kw,
    ):
        super().__init__(url, **kw)
        self.headers = headers
        self.proxy = proxy
        self.watch = asyncio.create_task(self.watchdog())
        self.basedir: Path = basedir
        self.auth_header: str = auth_header
        self.cf_clearance = cf_clearance

    async def watchdog(self, timeout=60):
        logger.debug("Emby 链接池看门狗启动.")
        try:
            counter = {}
            while True:
                await asyncio.sleep(10)
                for s, u in self._session_uses.items():
                    try:
                        if u and u <= 0:
                            if s in counter:
                                counter[s] += 1
                                if counter[s] >= timeout / 10:
                                    logger.debug("销毁了 Emby Session")
                                    async with await self._get_session_lock():
                                        counter[s] = 0
                                        await self._sessions[s].aclose()
                                        self._sessions[s] = None
                                        self._session_uses[s] = None
                            else:
                                counter[s] = 1
                        else:
                            counter.pop(s, None)
                    except (TypeError, KeyError):
                        pass
        except asyncio.CancelledError:
            for s in self._sessions.values():
                if s:
                    try:
                        await asyncio.wait_for(s.aclose(), 1)
                    except asyncio.TimeoutError:
                        pass

    async def _get_session(self):
        try:
            loop = asyncio.get_running_loop()
            loop_id = hash(loop)
            async with await self._get_session_lock():
                session = self._sessions.get(loop_id)
                if not session:

                    proxy = get_proxy_str(self.proxy)

                    cookies = {}
                    if self.cf_clearance:
                        cookies["cf_clearance"] = self.cf_clearance

                    timeout = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)

                    session = httpx.AsyncClient(
                        http2=True,
                        headers=self.headers,
                        cookies=cookies,
                        proxy=proxy,
                        verify=False,
                        follow_redirects=True,
                        timeout=timeout,
                    )
                    self._sessions[loop_id] = session
                    self._session_uses[loop_id] = 1
                    logger.debug("创建了新的 Emby Session.")
                else:
                    self._session_uses[loop_id] += 1
                return session
        except Exception as e:
            logger.error(f"无法创建 Emby Session: {e}")

    async def _end_session(self):
        loop = asyncio.get_running_loop()
        loop_id = hash(loop)
        async with await self._get_session_lock():
            self._session_uses[loop_id] -= 1

    async def _get_session_lock(self):
        loop = asyncio.get_running_loop()
        return self._session_locks.setdefault(loop, asyncio.Lock())

    async def _reset_session(self):
        async with await self._get_session_lock():
            loop = asyncio.get_running_loop()
            loop_id = hash(loop)
            self._sessions[loop_id] = None
            self._session_uses[loop_id] = 0

    @async_func
    async def login_if_needed(self):
        hostname = self.url.netloc
        cache_dir = self.basedir / "emby_tokens"
        cache_file = cache_dir / f"{hostname}_{self.username}.json"

        if not self.token:
            async with self.cache_lock:
                cache_dir.mkdir(exist_ok=True, parents=True)
                if cache_file.exists():
                    try:
                        data = json.loads(cache_file.read_text())
                        self.token = data["token"]
                        self.userid = data["userid"]
                        self.api_key = self.token
                    except (json.JSONDecodeError, OSError, KeyError) as e:
                        logger.debug(f"读取 Emby Token 缓存失败: {e}")

        if not self.token:
            return await self.login()

    @async_func
    async def login(self):
        if not self.username or self.attempt_login:
            return

        self.attempt_login = True
        try:
            data = await self.postJson(
                "/Users/AuthenticateByName",
                data={
                    "Username": self.username,
                    "Pw": self.password,
                },
                send_raw=True,
                format="json",
            )

            self.token = data.get("AccessToken", "")
            self.userid = data.get("User", {}).get("Id")
            self.api_key = self.token

            hostname = self.url.netloc
            cache_dir = self.basedir / "emby_tokens"
            cache_file = cache_dir / f"{hostname}_{self.username}.json"

            async with self.cache_lock:
                try:
                    cache_data = {
                        "token": self.token,
                        "userid": self.userid,
                    }
                    cache_file.write_text(json.dumps(cache_data, indent=2))
                except OSError as e:
                    logger.debug(f"保存 Emby Token 缓存失败: {e}")

        finally:
            self.attempt_login = False

    @async_func
    async def _req(self, method, path, params={}, **query):
        query.pop("format", None)
        await self.login_if_needed()
        session: httpx.AsyncClient = await self._get_session()
        full_auth_header = f'MediaBrowser Token={self.token or ""},Emby UserId={str(uuid.uuid4()).upper()},{self.auth_header}'
        session.headers["X-Emby-Authorization"] = full_auth_header
        if self.token:
            session.headers["X-Emby-Token"] = self.token
        for i in range(self.tries):
            url = self.get_url(path, **query)
            try:
                resp = await method(url, **params)
            except httpx.HTTPError as e:
                logger.debug(f'连接 "{url}" 失败, 即将重连: {e.__class__.__name__}: {e}')
            else:
                if self.attempt_login and resp.status_code == 401:
                    raise httpx.HTTPError("用户名密码错误")
                if await self._process_resp(resp):
                    return resp
            await asyncio.sleep(random.random() * i + 0.2)
        raise httpx.HTTPError("无法连接到服务器.")

    @async_func
    async def _process_resp(self, resp):
        if (not resp or resp.status_code == 401) and self.username:
            await self.login()
            return False
        if not resp:
            return False
        if resp.status_code in (502, 503, 504):
            await asyncio.sleep(random.random() * 4 + 0.2)
            return False
        return True

    @staticmethod
    @async_func
    async def resp_to_json(resp: httpx.Response):
        try:
            return json.loads(await resp.aread())
        except json.JSONDecodeError:
            raise httpx.HTTPError(
                'Unexpected JSON output (status: {}): "{}"'.format(
                    resp.status_code,
                    (await resp.aread()).decode(),
                )
            )

    @async_func
    async def get(self, path, **query):
        try:
            session = await self._get_session()
            resp: httpx.Response = await self._req(session.get, path, **query)
            return resp.status_code, (await resp.aread()).decode()
        finally:
            await self._end_session()

    @async_func
    async def delete(self, path, **query):
        try:
            session = await self._get_session()
            resp = await self._req(session.delete, path, **query)
            return resp.status_code
        finally:
            await self._end_session()

    @async_func
    async def _post(self, path, return_json, data, send_raw, **query):
        try:
            session = await self._get_session()
            if send_raw:
                params = {"json": data}
            else:
                params = {"data": json.dumps(data)}
            resp: httpx.Response = await self._req(session.post, path, params=params, **query)
            if return_json:
                return await Connector.resp_to_json(resp)
            else:
                return resp.status_code, (await resp.aread()).decode()
        finally:
            await self._end_session()

    @async_func
    async def get_stream_noreturn(self, path, **query):
        try:
            session = await self._get_session()
            url = self.get_url(path)
            async with session.stream(
                "GET",
                url,
                timeout=httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0),
                **query,
            ) as resp:
                async for _ in resp.aiter_bytes(chunk_size=4096):
                    await asyncio.sleep(random.uniform(5, 10))
        finally:
            await self._end_session()

    def get_url(self, path="/", websocket=False, remote=True, userId=None, pass_uid=False, **query):
        userId = userId or self.userid
        if pass_uid:
            query["userId"] = userId

        if remote:
            url = self.urlremote or self.url
        else:
            url = self.url

        if websocket:
            scheme = url.scheme.replace("http", "ws")
        else:
            scheme = url.scheme

        url = urlunparse((scheme, url.netloc, path, "", "{params}", "")).format(
            UserId=userId, ApiKey=self.api_key, params=urlencode(query)
        )

        return url[:-1] if url[-1] == "?" else url

    @async_func
    async def getJson(self, path, **query):
        try:
            session = await self._get_session()
            resp = await self._req(session.get, path, **query)
            return await Connector.resp_to_json(resp)
        finally:
            await self._end_session()


class Emby(_Emby):
    def __init__(self, url, **kw):
        """重写的 Emby 类, 以支持代理."""
        connector = Connector(url, **kw)
        EmbyObject.__init__(self, {"ItemId": "", "Name": ""}, connector)
        self._partial_cache = {}
        self._cache_lock = asyncio.Condition()

    @async_func
    async def get_items(
        self,
        types,
        path="/Users/{UserId}/Items",
        fields=None,
        limit=10,
        sort="SortName",
        ascending=True,
        **kw,
    ):
        if not fields:
            fields = ["Path", "ParentId", "Overview", "PremiereDate", "DateCreated"]
        resp = await self.connector.getJson(
            path,
            remote=False,
            format="json",
            recursive="true",
            includeItemTypes=",".join(types),
            fields=fields,
            sortBy=sort,
            sortOrder="Ascending" if ascending else "Descending",
            limit=limit,
            **kw,
        )
        return await self.process(resp)

    @async_func
    async def get_item(self, id, path="/Users/{UserId}/Items", fields=None, **kw):
        if not fields:
            fields = ["Path", "ParentId", "Overview", "PremiereDate", "DateCreated"]
        resp = await self.connector.getJson(
            f"{path}/{id}",
            format="json",
            recursive="true",
            fields=fields,
            **kw,
        )
        return await self.process(resp)
