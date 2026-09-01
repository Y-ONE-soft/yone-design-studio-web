# -*- coding: utf-8 -*-
"""완성 포켓북·분석본 .indd → .idml 일괄 내보내기.

**이 스크립트가 InDesign 을 쓰는 유일한 자리다.** 로직은 하나도 없다 —
열고, 내보내고, 저장 없이 닫는다. 이후 모든 해석은 파이썬이 IDML 로 한다.

⚠ GDrive 원본은 **열지 않는다.** 로컬 임시본으로 복사해 그걸 연다
  (전역 규칙: 구글 드라이브 파일 직접 수정·열기 금지). 복사가 끝나면 지운다.
⚠ 이어 돌리기 — 이미 만들어진 .idml 은 건너뛴다. 중간에 끊겨도 다시 돌리면 된다.
"""
import os
import shutil
import subprocess
import sys
import time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import idrun  # noqa: E402

GD = os.path.expanduser(
    "~/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/"
    "콘텐츠 관리/내신대비/인디자인 파일")
OUT = os.path.expanduser(
    "~/Documents/작업/Y.ONE STUDIO/조판/교재/포켓북/_idml")
# ⚠ 작업 사본을 `/private/tmp` 에 두면 안 된다. InDesign 을 강제 종료했다가
#   다시 띄우면 그 경로의 문서를 **"파일이 손상되었습니다(오류 코드 4)"** 로
#   전부 거부한다(실측: 같은 파일이 Documents 아래에서는 정상으로 열린다).
#   권한/샌드박스 문제라 파일 자체와는 무관하다.
TMP = os.path.expanduser(
    "~/Documents/작업/Y.ONE STUDIO/조판/교재/포켓북/_idml/_tmp")

SOURCES = {
    "pocketbook": os.path.join(GD, "포켓북"),
    "analysis": os.path.join(GD, "분석본"),
}

_JSX = '''
app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
var st = new File("%(status)s");
function say(s){ st.open("w"); st.encoding="UTF-8"; st.write(s); st.close(); }
try {
    var src = new File("%(src)s");
    if (!src.exists) { say("ERR|없음"); }
    else {
        var d = app.open(src, false);
        var dst = new File("%(dst)s");
        d.exportFile(ExportFormat.INDESIGN_MARKUP, dst);
        d.close(SaveOptions.NO);
        say(dst.exists ? "OK|" + dst.length : "ERR|내보내기 실패");
    }
} catch (e) {
    try { if (app.documents.length) app.documents[0].close(SaveOptions.NO); } catch(e2) {}
    say("ERR|" + e.message);
}
app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
'''


def _copy(src, dst):
    """GDrive → 로컬. cp 가 EDEADLK 로 죽는 사례가 있어 ditto 로 폴백한다."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        shutil.copyfile(src, dst)
        return True
    except OSError:
        pass
    for cmd in (["ditto", src, dst], ["cp", src, dst]):
        try:
            if subprocess.run(cmd, capture_output=True, timeout=600).returncode == 0 \
                    and os.path.exists(dst):
                return True
        except Exception:
            continue
    return False


_CLEAN_JSX = """
// **우리가 연 작업 사본만** 닫는다. 남의 문서는 건드리지 않는다.
var want = "%(work)s";
try {
  for (var i = app.documents.length - 1; i >= 0; i--) {
    var d = app.documents[i], p = "";
    try { p = d.fullName.fsName; } catch (e) { p = ""; }
    if (p === want) { d.close(SaveOptions.NO); }
  }
} catch (e) {}
"""


def _cleanup_docs():
    """우리가 연 작업 사본이 남아 있으면 저장 없이 닫는다.

    ⚠⚠ 예전에는 **열린 문서를 전부** 닫았다. 다른 세션이나 사용자가 InDesign 에
      문서를 열어 두면 그것까지 닫힌다 — 실제로 다른 세션의
      `성덕2_워크북03(26년6월)_내지.indd` 가 열려 있는 채로 이 배치가 돌 뻔했다.
      **경로가 우리 작업 사본과 정확히 같은 문서만** 닫는다.
    """
    try:
        work = os.path.join(TMP, "work.indd")
        p = os.path.join(TMP, "clean.jsx")
        with open(p, "w", encoding="utf-8") as f:
            f.write(_CLEAN_JSX % {"work": work})
        idrun.run_file(p, timeout=300)
    except Exception:
        pass


def _foreign_docs():
    """우리 작업 사본이 **아닌** 열린 문서 수. 무응답이면 -1."""
    js = os.path.join(TMP, "count.jsx")
    out = os.path.join(TMP, "count.txt")
    work = os.path.join(TMP, "work.indd")
    try:
        with open(js, "w", encoding="utf-8") as f:
            f.write('var n=0, want="%s";\n'
                    'for (var i=0;i<app.documents.length;i++){var p="";'
                    'try{p=app.documents[i].fullName.fsName;}catch(e){p="";}'
                    'if(p!==want) n++;}\n'
                    'var o=new File("%s"); o.open("w"); o.write(String(n)); o.close();\n'
                    % (work, out))
        if os.path.exists(out):
            os.remove(out)
        idrun.run_file(js, timeout=120)
        return int(open(out, encoding="utf-8").read().strip())
    except Exception:
        return -1


def scan(kind):
    root = SOURCES[kind]
    items = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if not fn.lower().endswith(".indd") or fn.startswith("."):
                continue
            src = os.path.join(dirpath, fn)
            rel = os.path.relpath(src, root)
            dst = os.path.join(OUT, kind, os.path.splitext(rel)[0] + ".idml")
            items.append((src, dst))
    items.sort(key=lambda x: x[0])
    return items


def export_one(src, dst, status_path, jsx_path, timeout=240):
    if os.path.exists(dst) and os.path.getsize(dst) > 10000:
        return "SKIP", 0
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = os.path.join(TMP, "work.indd")
    if os.path.exists(tmp):
        os.remove(tmp)
    if not _copy(src, tmp):
        return "ERR", "복사 실패"
    # GDrive 는 실체화가 덜 된 파일을 짧게 내주기도 한다 — 크기가 다르면 손상본이다.
    try:
        if os.path.getsize(tmp) != os.path.getsize(src):
            return "ERR", "복사본 크기 불일치(동기화 중)"
    except OSError:
        return "ERR", "복사본 확인 실패"
    if os.path.exists(status_path):
        os.remove(status_path)
    with open(jsx_path, "w", encoding="utf-8") as f:
        f.write(_JSX % {"src": tmp, "dst": dst, "status": status_path})

    # 두 번 죽은 파일은 다시 열지 않는다. 20MB 짜리 옛 아카이브 몇 권이
    # InDesign 을 통째로 멎게 해서 배치가 그 자리에서 멈춘다(실측).
    skip_path = os.path.join(TMP, "_skip.txt")
    key = os.path.basename(src)
    skips = set()
    if os.path.exists(skip_path):
        skips = set(open(skip_path, encoding="utf-8").read().splitlines())
    if key in skips:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return "ERR", "두 번 실패해 건너뜀"

    err = None
    for attempt in (1, 2):
        try:
            idrun.run_file(jsx_path, timeout=timeout)
            err = None
            break
        except subprocess.TimeoutExpired:
            err = "시간 초과(%ds)" % timeout
            restart_indesign()
        except Exception as e:
            err = str(e)[:200]
            # 실패본이 열린 채 남으면 **다음 파일까지 연달아 죽는다**(실측).
            _cleanup_docs()
            if idrun.open_doc_count() < 0:
                restart_indesign()
    if err is None:
        _cleanup_docs()
    try:
        os.remove(tmp)
    except OSError:
        pass
    if err:
        with open(skip_path, "a", encoding="utf-8") as f:
            f.write(key + "\n")
        return "ERR", err
    if not os.path.exists(status_path):
        return "ERR", "상태 없음"
    s = open(status_path, encoding="utf-8").read().strip()
    tag, _, rest = s.partition("|")
    return tag, rest


def main(kind, limit=None, log_path=None, only=None):
    items = scan(kind)
    if only:
        import unicodedata as _u
        needle = _u.normalize("NFC", only)
        items = [x for x in items
                 if needle in _u.normalize("NFC", x[0])]
    os.makedirs(TMP, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    if idrun.open_doc_count() < 0:      # 무응답 — 앞 배치가 멎어 있다
        restart_indesign()
    n_open = _foreign_docs()
    if n_open > 0:
        raise SystemExit(
            "InDesign 에 남의 문서가 %d개 열려 있다 — 사용자나 다른 세션의 "
            "작업물일 수 있으므로 닫지 않고 중단한다.\n"
            "  → 그 문서를 닫은 뒤 같은 명령을 다시 돌릴 것." % n_open)
    status = os.path.join(TMP, "status.txt")
    jsx = os.path.join(TMP, "one.jsx")
    log_path = log_path or os.path.join(OUT, "export_%s.log" % kind)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    done = ok = skip = err = 0
    t0 = time.time()
    with open(log_path, "a", encoding="utf-8") as lg:
        lg.write("=== %s · %d개 · %s ===\n"
                 % (kind, len(items), time.strftime("%m-%d %H:%M")))
        lg.flush()
        for src, dst in items:
            if limit and done >= limit:
                break
            done += 1
            tag, rest = export_one(src, dst, status, jsx)
            if tag == "OK":
                ok += 1
            elif tag == "SKIP":
                skip += 1
            else:
                err += 1
            name = unicodedata.normalize("NFC", os.path.basename(src))
            lg.write("[%4d/%4d] %-5s %s %s\n"
                     % (done, len(items), tag, name, rest if tag == "ERR" else ""))
            lg.flush()
        lg.write("→ 완료 %d · 건너뜀 %d · 실패 %d · %.0f분\n"
                 % (ok, skip, err, (time.time() - t0) / 60))
    print("완료 %d · 건너뜀 %d · 실패 %d" % (ok, skip, err))
    return ok, skip, err


if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 else "pocketbook"
    only = None
    lim = None
    for a in sys.argv[2:]:
        if a.startswith("--only="):
            only = a.split("=", 1)[1]
        else:
            lim = int(a)
    main(kind, lim, only=only)
