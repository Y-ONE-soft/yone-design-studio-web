# -*- coding: utf-8 -*-
"""Y.OS(contents·core)에 **일이 끝났다**고 알린다 — 웹훅.

    render.finished   조판 잡이 끝났다 (done / done_warn / failed)
    design.changed    디자인이 등록·수정·삭제됐다 → contents 는 카탈로그 캐시를 비운다

환경변수
    YOS_WEBHOOK_URL      받는 주소 (없으면 조용히 안 보낸다)
    YOS_WEBHOOK_SECRET   서명 키 (없으면 YOS_LINK_SECRET — 링크 토큰과 같은 비밀)

요청: POST JSON, 헤더 `x-studio-event: <이벤트>`, `x-studio-signature: <hex HMAC-SHA256(비밀, 본문)>`.
core 의 CHAT 연동(`src/server/chat/link.ts` — `x-chat-signature`)과 같은 규칙이라 그 `verifySignature` 를
그대로 복사해 쓰면 된다. 실패해도 여기서는 로그만 남긴다 — 알림이 조판을 막아선 안 되고,
contents 는 어차피 폴링으로도 결과를 가져갈 수 있다.
"""
import hashlib
import hmac
import json
import os
import threading
import time


def _url():
    return (os.environ.get("YOS_WEBHOOK_URL") or "").strip()


def _secret():
    s = (os.environ.get("YOS_WEBHOOK_SECRET") or "").strip()
    return s or (os.environ.get("YOS_LINK_SECRET") or "").strip()


def sign(body, secret=None):
    secret = secret if secret is not None else _secret()
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def send(event, payload, log=None, retries=3):
    """웹훅 하나를 보낸다(동기). 주소가 없으면 False."""
    url = _url()
    if not url:
        return False
    body = json.dumps({"event": event, "sent_at": time.time(), **payload}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "x-studio-event": event,
               "x-studio-signature": sign(body)}
    import requests
    delay = 2
    for i in range(retries):
        try:
            r = requests.post(url, data=body, headers=headers, timeout=10)
            if r.status_code < 300:
                return True
            if log:
                log(f"[웹훅] {event} → {r.status_code} ({i + 1}/{retries})")
        except Exception as e:                        # noqa: BLE001
            if log:
                log(f"[웹훅] {event} 실패: {e} ({i + 1}/{retries})")
        time.sleep(delay)
        delay *= 3
    return False


def send_async(event, payload, log=None):
    threading.Thread(target=send, args=(event, payload, log), daemon=True).start()


def design_changed(series, design, action, log=None):
    """디자인 등록·수정·삭제 뒤 한 줄. 실패해도 예외를 내지 않는다."""
    try:
        send_async("design.changed", {"series": series, "design": design, "action": action}, log)
    except Exception:
        pass
