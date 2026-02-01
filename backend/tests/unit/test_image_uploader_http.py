import base64
import urllib.parse

import httpx
import pytest

from app.infrastructure.external.image_uploader import ImgBBImageUploader, FreeImageHostUploader


def _parse_form(request: httpx.Request) -> dict:
    body = request.content.decode("utf-8")
    return urllib.parse.parse_qs(body)


@pytest.mark.asyncio
async def test_imgbb_uploader_posts_form(monkeypatch):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        form = _parse_form(request)
        assert form["key"][0] == "imgbb-key"
        assert form["name"][0] == "chart"
        assert "image" in form
        return httpx.Response(200, json={"data": {"url": "https://imgbb.example/chart.png"}})

    transport = httpx.MockTransport(handler)

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedAsyncClient)

    uploader = ImgBBImageUploader(api_key="imgbb-key", api_url="https://imgbb.example/upload")
    url = await uploader.upload(b"fake-bytes", "chart")
    await uploader.close()

    assert url == "https://imgbb.example/chart.png"
    assert len(captured) == 1
    assert captured[0].method == "POST"


@pytest.mark.asyncio
async def test_freeimage_uploader_posts_form(monkeypatch):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        form = _parse_form(request)
        assert form["key"][0] == "free-key"
        assert form["format"][0] == "json"
        assert form["name"][0] == "snapshot"
        decoded = base64.b64decode(form["source"][0])
        assert decoded == b"payload"
        return httpx.Response(200, json={"data": {"url": "https://free.example/snapshot.png"}})

    transport = httpx.MockTransport(handler)

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedAsyncClient)

    uploader = FreeImageHostUploader(api_key="free-key", api_url="https://free.example/upload")
    url = await uploader.upload(b"payload", "snapshot")
    await uploader.close()

    assert url == "https://free.example/snapshot.png"
    assert len(captured) == 1
