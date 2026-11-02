import asyncio
from typing import Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from .auth import require_auth
from .pm import pm

router = APIRouter()


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _filter_headers(headers: Dict[str, str]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for k, v in headers.items():
        lk = k.lower()
        if lk in HOP_BY_HOP_HEADERS or lk == "content-length" or lk == "host":
            continue
        result[k] = v
    return result


async def _close_stream(resp: httpx.Response, client: httpx.AsyncClient):
    await resp.aclose()
    await client.aclose()


@router.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_api(request: Request, path: str, _: bool = Depends(require_auth)):
    if not pm.host or not pm.port:
        raise HTTPException(status_code=503, detail="Backend target is not configured")

    target = f"http://{pm.host}:{pm.port}/api/{path}"

    method = request.method
    params = dict(request.query_params)
    headers = _filter_headers(dict(request.headers))
    accepts_event_stream = "text/event-stream" in request.headers.get("accept", "")

    body = await request.body()
    content = body if body else None

    try:
        if accepts_event_stream:
            client = httpx.AsyncClient(timeout=None, trust_env=False)
            proxy_request = client.build_request(
                method, target, params=params, headers=headers, content=content
            )
            resp = await client.send(proxy_request, stream=True)
            resp_headers = _filter_headers(dict(resp.headers))
            content_type = resp_headers.get("content-type")

            async def gen():
                try:
                    async for chunk in resp.aiter_bytes():
                        yield chunk
                except (asyncio.CancelledError, httpx.ReadError):
                    pass
                finally:
                    await _close_stream(resp, client)

            return StreamingResponse(
                gen(), status_code=resp.status_code, headers=resp_headers, media_type=content_type
            )

        async with httpx.AsyncClient(timeout=None, trust_env=False) as client:
            resp = await client.request(method, target, params=params, headers=headers, content=content)
            resp_headers = _filter_headers(dict(resp.headers))
            content_type = resp_headers.get("content-type")
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=resp_headers,
                media_type=content_type,
            )
    except httpx.ConnectError as e:
        raise HTTPException(status_code=503, detail=f"Failed to connect backend: {e}")
    except httpx.ReadError as e:
        raise HTTPException(status_code=502, detail=f"Backend stream interrupted: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proxy error: {e}")
