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
TMP = "/private/tmp/claude-501/_pocket_idml_tmp"

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


def export_one(src, dst, status_path, jsx_path, timeout=900):
    if os.path.exists(dst) and os.path.getsize(dst) > 10000:
        return "SKIP", 0
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = os.path.join(TMP, "work.indd")
    if os.path.exists(tmp):
        os.remove(tmp)
    if not _copy(src, tmp):
        return "ERR", "복사 실패"
    for p in (status_path,):
        if os.path.exists(p):
            os.remove(p)
    with open(jsx_path, "w", encoding="utf-8") as f:
        f.write(_JSX % {"src": tmp, "dst": dst, "status": status_path})
    try:
        idrun.run_file(jsx_path, timeout=timeout)
    except Exception as e:
        return "ERR", str(e)[:200]
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    if not os.path.exists(status_path):
        return "ERR", "상태 없음"
    s = open(status_path, encoding="utf-8").read().strip()
    tag, _, rest = s.partition("|")
    return tag, rest


def main(kind, limit=None, log_path=None):
    items = scan(kind)
    os.makedirs(TMP, exist_ok=True)
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
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else None
    main(kind, lim)
