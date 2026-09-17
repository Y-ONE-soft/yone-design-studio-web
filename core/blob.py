# -*- coding: utf-8 -*-
"""Vercel Blob 업로드 — contents·core 가 쓰는 **같은 스토어**에 산출물을 둔다.

contents 는 `@vercel/blob` 의 `put()` 으로 파일을 올리고 `blobUrl`/`pathname` 을 DB 에 적는다.
스튜디오는 Node 가 아니라 SDK 대신 같은 REST 를 부른다(SDK v2 · API 버전 12 와 같은 헤더).

    PUT https://vercel.com/api/blob/?pathname=<경로>
        authorization: Bearer <BLOB_READ_WRITE_TOKEN>   x-api-version: 12
        x-vercel-blob-store-id: <토큰의 storeId>        x-vercel-blob-access: private|public
        x-content-type · x-add-random-suffix
    → {url, downloadUrl, pathname, contentType, contentDisposition, etag}

환경변수
    BLOB_READ_WRITE_TOKEN   contents 와 같은 스토어의 읽기·쓰기 토큰(Vercel → Storage → Blob). 없으면 꺼짐
    YOS_BLOB_PREFIX         경로 앞머리(기본 studio) — contents 의 analysis-images/ 처럼 스튜디오 것을 한 폴더에
    YOS_BLOB_PDF_ACCESS     PDF 접근(기본 private — contents 의 exam-files 와 같다. 열람은 presignUrl 로)

private 로 올린 파일의 `url` 은 그대로는 안 열린다 — contents 가 `presignUrl(pathname)` 로 열어 준다
(`src/app/api/exam-files/[id]/download/route.ts` 와 같은 방식). public 은 URL 그대로 <img> 에 쓸 수 있다.
"""
import os
import urllib.parse

API = "https://vercel.com/api/blob"
API_VERSION = "12"


def _token():
    return (os.environ.get("BLOB_READ_WRITE_TOKEN") or "").strip()


def enabled():
    return bool(_token())


def _store_id(token):
    parts = token.split("_")
    return parts[3] if len(parts) > 3 else ""


def prefix():
    return (os.environ.get("YOS_BLOB_PREFIX") or "studio").strip().strip("/")


def put(pathname, data, content_type="application/octet-stream", access=None, random_suffix=True,
        timeout=120):
    """파일 하나 업로드 → {url, downloadUrl, pathname, …}. 꺼져 있으면 None, 실패면 RuntimeError."""
    tok = _token()
    if not tok:
        return None
    import requests
    access = access or "private"
    headers = {"authorization": "Bearer " + tok, "x-api-version": API_VERSION,
               "x-vercel-blob-store-id": _store_id(tok), "x-vercel-blob-access": access,
               "x-content-type": content_type, "x-add-random-suffix": "1" if random_suffix else "0",
               "x-allow-overwrite": "0" if random_suffix else "1"}
    full = prefix() + "/" + pathname.lstrip("/")
    r = requests.put(API + "/?" + urllib.parse.urlencode({"pathname": full}), data=data, headers=headers,
                     timeout=timeout)
    if r.status_code >= 300:
        raise RuntimeError(f"Blob 업로드 실패 (HTTP {r.status_code}): {r.text[:200]}")
    out = r.json()
    out["access"] = access
    return out


def put_file(path, pathname, content_type, access=None, random_suffix=True):
    with open(path, "rb") as f:
        return put(pathname, f.read(), content_type, access=access, random_suffix=random_suffix)


def pdf_access():
    return (os.environ.get("YOS_BLOB_PDF_ACCESS") or "private").strip()
