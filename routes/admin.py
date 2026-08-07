"""서버 진단/관리 + 원격 채팅 (app.py에서 분리, C2-9).

진단(/diagnose, /api/health, /api/diagnose, /api/indesign/start, /debug/*)과
Claude 채팅(/chat*)은 모두 원격 접속용 운영 도구라 한 블루프린트로 묶는다.
"""
import json
import os
import subprocess as _sp
import uuid

from flask import (Blueprint, Response, jsonify, render_template, request,
                   stream_with_context)

import config

bp = Blueprint("admin", __name__)


# ── 서버 진단 API ────────────────────────────────────────────────────────────

@bp.route("/diagnose")
def diagnose_page():
    return '''<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>서버 진단</title>
    <style>body{background:#111;color:#eee;font-family:sans-serif;max-width:600px;margin:40px auto;padding:0 20px}
    pre{background:#1a1a1a;padding:16px;border-radius:8px;overflow-x:auto;font-size:13px;line-height:1.6}
    button{background:#6366f1;color:#fff;border:none;padding:12px 24px;border-radius:8px;font-size:14px;cursor:pointer;margin:8px 4px 8px 0}
    button:disabled{opacity:.5} .ok{color:#22c55e} .bad{color:#f87171}
    h1{font-size:20px} .tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px}
    .tag.on{background:#22c55e22;color:#22c55e} .tag.off{background:#f8717122;color:#f87171}</style></head>
    <body><h1>서버 진단</h1>
    <div id="status">불러오는 중...</div>
    <div style="margin-top:16px">
      <button onclick="startID()">InDesign 실행</button>
      <button onclick="load()">새로고침</button>
    </div>
    <script>
    async function load(){
      var el=document.getElementById('status');
      el.textContent='불러오는 중...';
      try{
        var r=await fetch('/api/diagnose');
        if(!r.ok){el.innerHTML='<span class="bad">API 오류: '+r.status+'</span>';return;}
        var d=await r.json();
        var h='<p>InDesign: '+(d.indesign.indexOf('실행 중')>=0
          ?'<span class="tag on">'+d.indesign+'</span>'
          :'<span class="tag off">'+d.indesign+'</span>')+'</p>';
        h+='<p>tmp settings: '+((typeof d.tmp_settings==='string')?d.tmp_settings:d.tmp_settings.length+'개')+'</p>';
        h+='<h3>최근 작업</h3><pre>';
        (d.recent_jobs||[]).forEach(function(j){
          var ok=j.log.indexOf('완료')>=0;
          h+='<span class="'+(ok?'ok':'bad')+'">'+j.age+'</span> '+j.school+' ('+j.job+')\n  '+j.log+'\n\n';
        });
        h+='</pre>';
        el.innerHTML=h;
      }catch(e){el.innerHTML='<span class="bad">연결 실패: '+e.message+'</span>';}
    }
    async function startID(){
      try{
        var r=await fetch('/api/indesign/start',{method:'POST'});
        var d=await r.json();
        document.getElementById('status').innerHTML=d.ok
          ?'<span class="ok">'+d.app+' 실행 요청 완료 (10초 후 새로고침)</span>'
          :'<span class="bad">실패: '+d.error+'</span>';
        setTimeout(load,10000);
      }catch(e){document.getElementById('status').innerHTML='<span class="bad">연결 실패: '+e.message+'</span>';}
    }
    load();
    </script></body></html>'''


@bp.route("/api/health")
def api_health():
    """간단한 헬스체크 — 인증 없이 접근 가능. 외부 모니터링/Tailscale 등에서 사용."""
    import subprocess as _hsp, time as _htime
    info = {"ok": True}

    # InDesign 가동 여부 (3초 timeout)
    info["indesign_running"] = False
    for ver in ("2026", "2025", "2024"):
        try:
            r = _hsp.run(
                ["osascript", "-e", f'tell application "Adobe InDesign {ver}" to return running'],
                capture_output=True, text=True, timeout=3
            )
            if "true" in r.stdout.lower():
                info["indesign_running"] = True
                info["indesign_version"] = ver
                break
        except Exception:
            continue

    # 활성 작업 (jobs/ 5분 내 수정된 폴더 수)
    jobs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "jobs")
    active = 0
    if os.path.isdir(jobs_dir):
        cutoff = _htime.time() - 300
        try:
            for d in os.listdir(jobs_dir):
                full = os.path.join(jobs_dir, d)
                if os.path.isdir(full) and os.path.getmtime(full) > cutoff:
                    active += 1
        except Exception:
            pass
    info["active_jobs"] = active

    # 마지막 자동 git pull
    pull_log = os.path.expanduser("~/Library/Logs/yone-auto-pull.log")
    if os.path.exists(pull_log):
        info["last_auto_pull"] = _htime.strftime(
            "%Y-%m-%d %H:%M:%S", _htime.localtime(os.path.getmtime(pull_log))
        )

    # 주요 환경변수 (값은 노출 X, 설정 여부만)
    info["env"] = {
        "YONE_STUDIO_ROOT": bool(os.environ.get("YONE_STUDIO_ROOT")),
        "YONE_ADMIN_PASSWORD": bool(os.environ.get("YONE_ADMIN_PASSWORD")),
        "YONE_ASSISTANT_PASSWORD": bool(os.environ.get("YONE_ASSISTANT_PASSWORD")),
        "YONE_SECRET_KEY": bool(os.environ.get("YONE_SECRET_KEY")),
        "ASSISTANT_SHARE_DIR": bool(os.environ.get("ASSISTANT_SHARE_DIR")),
    }

    return jsonify(info)


@bp.route("/api/diagnose")
def api_diagnose():
    """아이맥 서버 상태 진단 — InDesign, /tmp, 최근 작업 확인."""
    import subprocess, glob as _glob, time as _time
    info = {}

    # 1) InDesign 실행 여부
    for ver in ["2026", "2025", "2024", "2023"]:
        app_name = f"Adobe InDesign {ver}"
        try:
            r = subprocess.run(
                ["osascript", "-e", f'tell application "{app_name}" to return running'],
                capture_output=True, text=True, timeout=3
            )
            if "true" in r.stdout or "running" in r.stdout:
                info["indesign"] = f"{app_name} (실행 중)"
                break
        except Exception:
            continue
    else:
        info["indesign"] = "InDesign 미실행"

    # 2) /tmp/pocketbook_* 파일
    tmp_files = _glob.glob("/tmp/pocketbook_*/settings.json")
    info["tmp_settings"] = tmp_files if tmp_files else "없음"

    # 3) 최근 3개 작업 상태
    jobs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "jobs")
    recent = []
    if os.path.isdir(jobs_dir):
        job_ids = sorted(os.listdir(jobs_dir),
                         key=lambda x: os.path.getmtime(os.path.join(jobs_dir, x))
                         if os.path.isdir(os.path.join(jobs_dir, x)) else 0,
                         reverse=True)[:3]
        for jid in job_ids:
            jdir = os.path.join(jobs_dir, jid)
            if not os.path.isdir(jdir):
                continue
            log_path = os.path.join(jdir, "typeset_log.txt")
            school_path = os.path.join(jdir, "school.txt")
            school = open(school_path).read().strip() if os.path.exists(school_path) else "?"
            has_log = os.path.exists(log_path)
            log_tail = ""
            if has_log:
                lines = open(log_path, encoding="utf-8", errors="ignore").readlines()
                log_tail = (lines[-1].strip() if lines else "")
            age = int(_time.time() - os.path.getmtime(jdir))
            recent.append({
                "job": jid, "school": school,
                "log": log_tail if has_log else "로그 없음 (JSX 미실행)",
                "age": f"{age // 60}분 전",
            })
    info["recent_jobs"] = recent

    return jsonify(info)


@bp.route("/api/indesign/start", methods=["GET", "POST"])
def api_indesign_start():
    """InDesign 원격 실행."""
    import subprocess
    for ver in ["2026", "2025", "2024", "2023"]:
        app_name = f"Adobe InDesign {ver}"
        if os.path.isdir(f"/Applications/{app_name}"):
            try:
                subprocess.Popen(
                    ["osascript", "-e", f'tell application "{app_name}" to activate'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                return jsonify({"ok": True, "app": app_name})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)})
    return jsonify({"ok": False, "error": "InDesign 설치를 찾을 수 없습니다"})


@bp.route("/debug/safecopy")
def debug_safecopy():
    """[임시 진단] _gdrive_safe_copy를 실제 파이프라인 흐름대로 호출."""
    import os, time, threading
    from engines.final.extractor import _gdrive_safe_copy
    # 실제 사용자 작업에서 실패한 파일로 변경
    F = ('/Users/nhj/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/'
         '내 드라이브/콘텐츠 관리/내신대비/'
         '인디자인 파일/워크북/모의고사/고1/'
         '고1_25년_3월_전체.indd')
    out = []
    out.append(f"PID: {os.getpid()}, thread: {threading.current_thread().name}")
    out.append("")

    # 메인 스레드 (Flask request thread)에서 호출
    out.append("=== 메인 스레드 (Flask request thread) ===")
    dst = f"/tmp/debug_safecopy_main_{os.getpid()}.docx"
    if os.path.exists(dst): os.remove(dst)
    t0 = time.time()
    captured = []
    ok, err = _gdrive_safe_copy(F, dst, log=lambda m: captured.append(m))
    out.append(f"결과: ok={ok}, time={time.time()-t0:.2f}s")
    out.append(f"dst size: {os.path.getsize(dst) if os.path.exists(dst) else 0}")
    if captured:
        out.append("로그:")
        out.extend(["  " + l for l in captured])
    if not ok:
        out.append(f"마지막 err: {err[:500]}")
    if os.path.exists(dst): os.remove(dst)
    out.append("")

    # 백그라운드 스레드 (실제 파이프라인 패턴)에서 호출
    out.append("=== 백그라운드 스레드 (daemon=True, 실제 파이프라인 패턴) ===")
    result = {}
    captured2 = []
    def worker():
        dst2 = f"/tmp/debug_safecopy_thread_{os.getpid()}.docx"
        if os.path.exists(dst2): os.remove(dst2)
        t = time.time()
        ok2, err2 = _gdrive_safe_copy(F, dst2,
                                      log=lambda m: captured2.append(m))
        result["ok"] = ok2
        result["err"] = err2
        result["time"] = time.time() - t
        result["size"] = os.path.getsize(dst2) if os.path.exists(dst2) else 0
        result["thread"] = threading.current_thread().name
        if os.path.exists(dst2): os.remove(dst2)

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    th.join(timeout=180)
    out.append(f"thread name: {result.get('thread', 'TIMEOUT')}")
    out.append(f"결과: ok={result.get('ok')}, time={result.get('time', 0):.2f}s")
    out.append(f"dst size: {result.get('size', 0)}")
    if captured2:
        out.append("로그:")
        out.extend(["  " + l for l in captured2])
    if not result.get('ok'):
        out.append(f"마지막 err: {str(result.get('err', ''))[:500]}")
    return "<pre>" + "\n".join(out) + "</pre>"


# ── Claude 채팅 (원격 접속용) ────────────────────────────────────────

_CONV_FILE = os.path.join(os.path.expanduser("~"), ".claude-desktop-data.json")

def _load_convs():
    try:
        with open(_CONV_FILE, encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"conversations": []}

def _save_convs(data):
    with open(_CONV_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

@bp.route("/chat")
def chat_page():
    return render_template("chat.html", active_nav="채팅")

@bp.route("/chat/folders")
def chat_folders():
    """작업 폴더 목록 반환."""
    base = config.STUDIO_ROOT
    try:
        dirs = [{"name": d, "path": os.path.join(base, d)}
                for d in sorted(os.listdir(base))
                if os.path.isdir(os.path.join(base, d)) and not d.startswith('.')]
        return jsonify(dirs)
    except Exception:
        return jsonify([])

@bp.route("/chat/conversations")
def chat_conversations():
    """데스크탑 앱 대화 목록 반환."""
    data = _load_convs()
    convs = data.get("conversations", [])
    return jsonify([{
        "id": c.get("id"),
        "title": c.get("title", "새 대화"),
        "sessionId": c.get("sessionId"),
        "workingDir": c.get("workingDir"),
        "messageCount": len(c.get("messages", [])),
        "createdAt": c.get("createdAt"),
    } for c in convs[:30]])

@bp.route("/chat/conversations/<conv_id>/messages")
def chat_messages(conv_id):
    """특정 대화의 메시지 반환."""
    data = _load_convs()
    conv = next((c for c in data.get("conversations", []) if c.get("id") == conv_id), None)
    if not conv:
        return jsonify({"error": "not found"}), 404
    msgs = conv.get("messages", [])
    return jsonify({
        "sessionId": conv.get("sessionId"),
        "workingDir": conv.get("workingDir"),
        "messages": [{"role": m.get("role"), "content": m.get("content", ""), "timestamp": m.get("timestamp")}
                     for m in msgs if m.get("role") in ("user", "assistant") and m.get("content")]
    })

@bp.route("/chat/conversations/<conv_id>/append", methods=["POST"])
def chat_append(conv_id):
    """웹에서 보낸 메시지/응답을 데스크탑 대화에 추가."""
    body = request.json or {}
    data = _load_convs()
    conv = next((c for c in data.get("conversations", []) if c.get("id") == conv_id), None)
    if not conv:
        return jsonify({"error": "not found"}), 404
    msg = {
        "id": str(uuid.uuid4())[:8],
        "role": body.get("role", "user"),
        "content": body.get("content", ""),
        "timestamp": int(body.get("timestamp", 0)) or int(__import__('time').time() * 1000),
    }
    conv.setdefault("messages", []).append(msg)
    if body.get("sessionId"):
        conv["sessionId"] = body["sessionId"]
    _save_convs(data)
    return jsonify({"ok": True})

@bp.route("/chat/watch/<conv_id>")
def chat_watch(conv_id):
    """SSE: 대화 변경 실시간 감지. 메시지 수가 바뀌면 새 메시지 전송."""
    import time as _time
    def generate():
        last_count = 0
        last_mtime = 0
        while True:
            try:
                mtime = os.path.getmtime(_CONV_FILE)
                if mtime != last_mtime:
                    last_mtime = mtime
                    data = _load_convs()
                    conv = next((c for c in data.get("conversations", []) if c.get("id") == conv_id), None)
                    if conv:
                        msgs = [m for m in conv.get("messages", []) if m.get("role") in ("user", "assistant") and m.get("content")]
                        if len(msgs) != last_count:
                            new_msgs = msgs[last_count:] if last_count > 0 else msgs[-1:]
                            last_count = len(msgs)
                            for m in new_msgs:
                                yield f"data: {json.dumps({'role': m['role'], 'content': m['content']}, ensure_ascii=False)}\n\n"
            except Exception:
                pass
            _time.sleep(2)
    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@bp.route("/chat/conversations/create", methods=["POST"])
def chat_create_conv():
    """웹에서 새 대화 생성 → 데스크탑 앱 데이터에 저장."""
    body = request.json or {}
    import time as _t
    conv_id = str(uuid.uuid4())[:8] + str(int(_t.time()))[-4:]
    data = _load_convs()
    conv = {
        "id": conv_id,
        "title": body.get("title", "새 대화")[:40],
        "messages": [],
        "sessionId": None,
        "workingDir": body.get("workingDir") or config.STUDIO_ROOT,
        "createdAt": int(_t.time() * 1000),
    }
    data.setdefault("conversations", []).insert(0, conv)
    _save_convs(data)
    return jsonify({"id": conv_id})

@bp.route("/chat/send", methods=["POST"])
def chat_send():
    """Claude CLI 실행 후 SSE 스트리밍 응답."""
    data = request.json or {}
    message = data.get("message", "").strip()
    session_id = data.get("sessionId")
    working_dir = data.get("workingDir") or config.STUDIO_ROOT

    if not message:
        return Response("data: {\"type\":\"error\",\"content\":\"빈 메시지\"}\n\ndata: [DONE]\n\n",
                        mimetype="text/event-stream")

    claude_path = os.path.join(os.path.expanduser("~"), ".local", "bin", "claude")
    args = [claude_path, "--dangerously-skip-permissions", "-p", message,
            "--output-format", "stream-json", "--verbose"]
    if session_id:
        args.extend(["--resume", session_id])

    def generate():
        try:
            proc = _sp.Popen(args, cwd=working_dir,
                             stdout=_sp.PIPE, stderr=_sp.PIPE,
                             text=True, env={**os.environ, "LANG": "ko_KR.UTF-8"})
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    # 세션 ID 전달
                    if ev.get("type") == "system" and ev.get("session_id"):
                        yield f"data: {json.dumps({'type':'session','sessionId':ev['session_id']})}\n\n"
                    # 텍스트 스트리밍
                    elif ev.get("type") == "assistant" and ev.get("message"):
                        content = ev["message"].get("content", [])
                        for block in content:
                            if block.get("type") == "text" and block.get("text"):
                                yield f"data: {json.dumps({'type':'text','content':block['text']})}\n\n"
                    elif ev.get("type") == "result" and ev.get("result"):
                        yield f"data: {json.dumps({'type':'text','content':ev['result']})}\n\n"
                except json.JSONDecodeError:
                    pass
            proc.wait()
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','content':str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
