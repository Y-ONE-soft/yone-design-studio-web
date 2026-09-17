# -*- coding: utf-8 -*-
"""Y.OS contents 에서 데이터를 읽어 오는 어댑터 — **매핑 코드는 여기 한 곳에만.**

스튜디오 화면의 "contents 에서 가져오기"도, contents 화면의 "조판" 단추도 결국 이 함수를
지난다. contents 는 자기 읽기 API 만 유지하면 되고, 틀별 data.json 구조는 여기서 맞춘다.

환경변수
    YOS_CONTENTS_API     contents 주소 (예: https://contents.yos.kr)
    YOS_CONTENTS_TOKEN   contents 가 스튜디오에 준 서비스 토큰 (없으면 YOS_SERVICE_TOKENS 첫 토큰)

계약 (contents 가 열어 줄 읽기 API — `deploy/README.md` 의 "contents 데이터 API" 절):

    GET {YOS_CONTENTS_API}/api/typeset/data?series=<틀>&<params…>
    Authorization: Bearer <YOS_CONTENTS_TOKEN>

    200 → {"kind": "data" | "plan", "data": {…}, "meta": {"title": …, "school": …, "period": …}}
          kind=data  → 그 틀의 data.json 을 그대로 (틀별 스키마: GET /api/v1/catalog/<틀>/schema)
          kind=plan  → 워크북 v2 render_plan.json
    4xx → {"error": "…"}  (범위 미확정 등 — 조판을 멈추고 그 말을 그대로 보여 준다)

지금은 contents 가 data.json 꼴을 **그대로** 내주는 것을 전제로 한다. 계열별 변환이 필요해지면
아래 `_ADAPTERS` 에 `series → fn(raw) -> data` 를 추가한다(파서 출력과 같은 꼴로 맞추는 자리).
"""
import os

from core.sources import SourceError

_ADAPTERS = {}       # series → callable(raw_json) -> data.json dict


def _api():
    return (os.environ.get("YOS_CONTENTS_API") or "").strip().rstrip("/")


def _token():
    t = (os.environ.get("YOS_CONTENTS_TOKEN") or "").strip()
    return t or (os.environ.get("YOS_SERVICE_TOKENS") or "").split(",")[0].strip()


def configured():
    return bool(_api())


def fetch(series, params, log=None):
    """contents → (kind, obj). 설정이 없거나 contents 가 거절하면 SourceError."""
    if not configured():
        raise SourceError("YOS_CONTENTS_API 가 없다 — contents 연동이 아직 설정되지 않았다")
    import requests
    q = {"series": series}
    q.update({k: v for k, v in (params or {}).items() if v not in (None, "")})
    if log:
        log(f"[contents] {series} ← {', '.join(f'{k}={v}' for k, v in q.items() if k != 'series')}")
    try:
        r = requests.get(_api() + "/api/typeset/data", params=q, timeout=60,
                         headers={"Authorization": "Bearer " + _token(), "Accept": "application/json"})
    except Exception as e:                                # noqa: BLE001
        raise SourceError(f"contents 에 닿지 못했다: {e}")
    try:
        body = r.json()
    except ValueError:
        raise SourceError(f"contents 응답이 JSON 이 아니다 (HTTP {r.status_code})")
    if r.status_code >= 400:
        raise SourceError(body.get("error") or f"contents 가 거절했다 (HTTP {r.status_code})")
    kind = body.get("kind") or "data"
    obj = body.get("data")
    if kind not in ("data", "plan") or not isinstance(obj, dict):
        raise SourceError("contents 응답에 kind(data|plan) 와 data 객체가 있어야 한다")
    if series in _ADAPTERS:
        obj = _ADAPTERS[series](obj)
    meta = body.get("meta") or {}
    if meta and log:
        log(f"[contents] {meta.get('school', '')} {meta.get('title', '')} {meta.get('period', '')}".strip())
    return kind, obj
