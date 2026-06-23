"""파이널 직전보충 — 워크북 .indd에서 텍스트 추출.

워크북 파일을 InDesign으로 열고, 단락 스타일 기반으로
문장배열/어법수정/영작배열 텍스트를 JSON으로 추출한다.
"""

import json
import os
import shutil
import subprocess
import time
import unicodedata


# ── 로컬 미러 redirect — EDEADLK 원천 차단 ─────────────────────────────────
# 자주 쓰는 GDrive 폴더를 로컬 미러로 복사해두면 어떤 클라우드 File Provider
# (Google Drive / iCloud)도 거치지 않아 deadlock 자체가 발생하지 않는다.
#
# [중요] 미러는 반드시 iCloud "데스크탑 및 문서" 동기화 영역 밖에 둔다.
#   과거 ~/Documents/yone-content-mirror 는 iCloud가 동기화해 파일 91%를 dataless로
#   비워버렸고, 그러면 미러를 읽을 때마다 이번엔 iCloud NSFileProvider 경유로
#   EDEADLK가 재발했다(Drive 재시작·재시도 다 무력). ~/Library/Application Support
#   와 홈 루트(~/)는 iCloud 미동기화라 안전.
#   (2026-06-02: ~/Documents → ~/Library/Application Support 로 이전.)
#   YONE_MIRROR_BASE 환경변수로 override 가능.
# 미러가 있으면 우회, 없으면 원본 그대로 사용.
_LOCAL_MIRROR_BASE = os.path.expanduser(
    os.environ.get(
        "YONE_MIRROR_BASE",
        "~/Library/Application Support/yone-design-web/content-mirror",
    )
)
_GDRIVE_CONTENT_MARKER = "/내 드라이브/콘텐츠 관리/내신대비/"


def _resolve_local_mirror(src, log=None):
    """GDrive 경로를 로컬 미러로 redirect (미러가 존재할 때만)."""
    nfc_src = unicodedata.normalize("NFC", src)
    if _GDRIVE_CONTENT_MARKER not in nfc_src:
        if log:
            log(f"  [DEBUG mirror] marker NOT in src → return as-is")
        return src
    rest = nfc_src.split(_GDRIVE_CONTENT_MARKER, 1)[1]
    mirror_path = os.path.join(_LOCAL_MIRROR_BASE, rest)
    if log:
        log(f"  [DEBUG mirror] mirror_path={mirror_path!r}")
    for cand in [
        mirror_path,
        unicodedata.normalize("NFC", mirror_path),
        unicodedata.normalize("NFD", mirror_path),
    ]:
        exists = os.path.exists(cand)
        if log:
            log(f"  [DEBUG mirror] cand exists={exists}: {cand!r}")
        if exists:
            if os.path.isdir(cand):
                try:
                    if not os.listdir(cand):
                        if log:
                            log(f"  [로컬 미러] {os.path.basename(cand)} 비어있음 → GDrive 원본 사용")
                        return src
                except OSError:
                    return src
            if log:
                log(f"  [로컬 미러] GDrive 우회 → {os.path.basename(cand)}")
            return cand
    if log:
        log(f"  [DEBUG mirror] no cand exists → return GDrive src")
    return src


def list_manuscript_entries(orig_folder, log=None):
    """원고 폴더 엔트리(파일/하위폴더)를 '미러 + GDrive 원본' 합집합으로 열거.

    미러는 1회성 스냅샷이라, GDrive에 나중에 추가된 파일(예: 'Step3.hwpx')이
    미러엔 없을 수 있다. 기존 코드는 미러 폴더만 listdir 해서 그런 파일을
    조용히 누락시켰다(공백/단어 차이가 아니라 '미러에 아예 없음'이 원인).
    이 함수는 미러에 없는 GDrive 전용 파일을 합집합으로 보강해 누락을 막는다.

    - 각 엔트리의 읽기 경로(src): 미러본이 있으면 미러(빠르고 EDEADLK 회피),
      없으면 GDrive 원본.
    - GDrive listdir이 EDEADLK 등으로 실패하면 미러만으로 진행하되 로그를 남긴다
      (조용한 누락 금지 — 무엇을 못 봤는지 항상 노출).

    Returns: 정렬된 [(name_nfc, src_path), ...] (파일·하위폴더 모두 포함)
    """
    mirror_folder = _resolve_local_mirror(orig_folder, log=None)
    entries = {}  # name_nfc -> src_path (미러 우선)

    if mirror_folder and os.path.isdir(mirror_folder):
        try:
            for raw in os.listdir(mirror_folder):
                n = unicodedata.normalize("NFC", raw)
                if n.startswith("."):
                    continue
                entries[n] = os.path.join(mirror_folder, raw)
        except OSError as e:
            if log:
                log(f"  [원고목록] 미러 listdir 실패: {e}")

    # GDrive 원본과 합집합 — 미러에 없는 파일 보강 (미러가 원본과 다를 때만)
    if orig_folder and orig_folder != mirror_folder and os.path.isdir(orig_folder):
        try:
            gdrive_only = []
            for raw in os.listdir(orig_folder):
                n = unicodedata.normalize("NFC", raw)
                if n.startswith("."):
                    continue
                if n not in entries:
                    entries[n] = os.path.join(orig_folder, raw)
                    gdrive_only.append(n)
            if gdrive_only and log:
                log(f"  [원고목록] 미러에 없어 GDrive에서 보강 {len(gdrive_only)}개: "
                    f"{', '.join(gdrive_only)}")
        except OSError as e:
            if log:
                log(f"  [원고목록] GDrive listdir 실패 → 미러만 사용: {e}")

    return sorted(entries.items())


def _gdrive_safe_copy(src, dst, log=None, retries=5):
    """Google Drive Stream 파일을 dst로 안정적으로 복사.

    Drive Stream FS는 File Provider extension 기반으로, 동시 read 요청 시
    EDEADLK(Errno 11, Resource deadlock avoided) 등 일시적 락 오류를
    반환할 수 있다.

    처방:
      1) 로컬 미러 redirect — ~/Documents/yone-content-mirror/에 미러가 있으면 우회
      2) Python pure read/write — shutil.copy2(fcopyfile)이 Flask launchd thread
         컨텍스트에서 hang하는 케이스 회피 (standalone/직접 thread는 정상이지만
         launchd LaunchAgent context의 워커 thread에서는 fcopyfile이 무한 wait
         가능). chunked read/write로 명시적 진행, 단계별 timestamp 로그로
         hang 시 정확한 위치 파악 가능.
      3) 지수 백오프(1+3+8+15+30초, 누적 57초) 재시도

    Returns: (ok: bool, last_err: str)
    """
    if log:
        log(f"  [DEBUG] _gdrive_safe_copy src_before={src!r}")
    src = _resolve_local_mirror(src, log)
    if log:
        log(f"  [DEBUG] _gdrive_safe_copy src_after ={src!r}")
        log(f"  [DEBUG] src is local mirror? {_LOCAL_MIRROR_BASE in src}")

    # NFD/NFC 후보 모두 시도 (macOS APFS는 NFD)
    src_candidates = [src]
    nfc = unicodedata.normalize("NFC", src)
    nfd = unicodedata.normalize("NFD", src)
    if nfc != src and nfc not in src_candidates:
        src_candidates.append(nfc)
    if nfd != src and nfd not in src_candidates:
        src_candidates.append(nfd)
    src_resolved = None
    for cand in src_candidates:
        if os.path.exists(cand):
            src_resolved = cand
            break
    if src_resolved is None:
        return False, f"소스 파일 없음: {src}"

    expected_size = os.path.getsize(src_resolved)
    backoffs = [1, 3, 8, 15, 30]
    last_err = ""

    def _chunk_copy(src_path, dst_path):
        """Python pure chunked copy — fcopyfile syscall 우회.

        Flask launchd worker thread에서 fcopyfile이 hang하는 케이스 회피.
        각 단계마다 timestamp 출력해서 hang 시 정확한 위치 파악.
        """
        import time as _t
        t0 = _t.time()
        with open(src_path, "rb") as fsrc:
            t_open_src = _t.time() - t0
            with open(dst_path, "wb") as fdst:
                t_open_dst = _t.time() - t0
                total = 0
                while True:
                    chunk = fsrc.read(64 * 1024)
                    if not chunk:
                        break
                    fdst.write(chunk)
                    total += len(chunk)
                t_write = _t.time() - t0
        # copystat은 별도 — atime/mtime 복사 (실패해도 데이터는 OK)
        try:
            shutil.copystat(src_path, dst_path)
        except Exception:
            pass
        if log:
            log(f"  [복사 timing] src_open={t_open_src:.2f}s "
                f"dst_open={t_open_dst:.2f}s write={t_write:.2f}s "
                f"size={total}B")
        return total

    for attempt in range(retries):
        try:
            if os.path.exists(dst):
                os.remove(dst)
            actual = _chunk_copy(src_resolved, dst)
            if actual == expected_size:
                if log and attempt > 0:
                    log(f"  [GDrive 복사] 성공 ({attempt+1}회차)")
                return True, ""
            last_err = f"부분 복사: src={expected_size}B dst={actual}B"
        except OSError as e:
            last_err = f"{type(e).__name__}: {e}"

        if log:
            log(f"  [GDrive 복사] 실패 ({attempt+1}/{retries}): {last_err}")
        if attempt < retries - 1:
            time.sleep(backoffs[min(attempt, len(backoffs) - 1)])

    # Python read(2) 전부 실패 → 별도 프로세스 / GUI 세션 폴백 (다단계).
    # launchd 컨텍스트의 워커 스레드에서 Drive Stream 미적재 파일을 materialize할 때
    # EDEADLK(Errno 11)가 나는데, python read·/bin/cp -c(clonefile)는 같은 데드락에
    # 막힌다(실측: cp -c → "clonefile failed: Resource deadlock avoided").
    # ditto(별도 프로세스)·Finder(GUI 세션 복사)가 이 컨텍스트 데드락을 우회하는
    # 케이스가 있어 순차 폴백한다. (clonefile을 직접 부르는 cp -c는 사용하지 않음)

    # 1) ditto — macOS 네이티브, FUSE 호환성 우수, clonefile 미사용
    try:
        if os.path.exists(dst):
            os.remove(dst)
        res = subprocess.run(
            ["/usr/bin/ditto", src_resolved, dst],
            capture_output=True, text=True, timeout=300
        )
        if res.returncode == 0 and os.path.exists(dst) \
                and os.path.getsize(dst) == expected_size:
            if log:
                log("  [GDrive 복사] ditto 폴백 성공")
            return True, ""
        ditto_err = (res.stderr or res.stdout or "").strip() or f"rc={res.returncode}"
        last_err = f"{last_err} / ditto 폴백 실패: {ditto_err}"
        if log:
            log(f"  [GDrive 복사] ditto 폴백 실패: {ditto_err}")
    except (OSError, subprocess.SubprocessError) as e:
        last_err = f"{last_err} / ditto 폴백 예외: {type(e).__name__}: {e}"
        if log:
            log(f"  [GDrive 복사] ditto 폴백 예외: {e}")

    # 2) Finder duplicate (AppleScript) — GUI 세션의 Finder가 복사하므로
    #    launchd 워커 스레드의 File Provider materialize 데드락을 우회한다.
    try:
        if os.path.exists(dst):
            os.remove(dst)
        dst_dir = os.path.dirname(dst) or "."
        osa = ('tell application "Finder" to duplicate '
               f'(POSIX file "{src_resolved}" as alias) '
               f'to (POSIX file "{dst_dir}" as alias) with replacing')
        res = subprocess.run(
            ["/usr/bin/osascript", "-e", osa],
            capture_output=True, text=True, timeout=300
        )
        # Finder는 원본 파일명으로 복사 → dst 이름으로 이동
        finder_copied = os.path.join(dst_dir, os.path.basename(src_resolved))
        if os.path.exists(finder_copied) and finder_copied != dst:
            if os.path.exists(dst):
                os.remove(dst)
            os.rename(finder_copied, dst)
        if os.path.exists(dst) and os.path.getsize(dst) == expected_size:
            if log:
                log("  [GDrive 복사] Finder 폴백 성공")
            return True, ""
        finder_err = (res.stderr or "").strip() or "복사물 없음/크기 불일치"
        last_err = f"{last_err} / Finder 폴백 실패: {finder_err}"
        if log:
            log(f"  [GDrive 복사] Finder 폴백 실패: {finder_err}")
    except (OSError, subprocess.SubprocessError) as e:
        last_err = f"{last_err} / Finder 폴백 예외: {type(e).__name__}: {e}"
        if log:
            log(f"  [GDrive 복사] Finder 폴백 예외: {e}")

    return False, last_err


def _find_app():
    for ver in ["2026", "2025", "2024"]:
        if os.path.isdir(f"/Applications/Adobe InDesign {ver}"):
            return f"Adobe InDesign {ver}"
    raise RuntimeError("InDesign을 찾을 수 없습니다.")


def _jsx(app_name, code, timeout=30, retries=3):
    """작은 JSX 코드를 InDesign에서 실행."""
    escaped = code.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    script = f'tell application "{app_name}" to do script "{escaped}" language javascript'

    for attempt in range(retries):
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            time.sleep(3)
            continue

        if result.returncode == 0:
            return result.stdout.strip()

        stderr = result.stderr.strip()
        if "30486" in stderr:
            _dismiss_indesign_dialogs(app_name)
            time.sleep(3)
            continue
        if "-609" in stderr:
            time.sleep(5)
            continue

        raise RuntimeError(f"JSX 에러: {stderr[:200]}")

    raise RuntimeError("JSX 재시도 횟수 초과")


def _dismiss_indesign_dialogs(app_name):
    try:
        subprocess.run(
            ["osascript", "-e", f'''
                tell application "{app_name}" to activate
                delay 0.5
                try
                    tell application "System Events"
                        tell process "{app_name}"
                            set frontmost to true
                            delay 0.5
                            click button 1 of window 1
                        end tell
                    end tell
                on error
                    try
                        tell application "System Events" to key code 36
                    end try
                end try
            '''],
            capture_output=True, text=True, timeout=10
        )
    except Exception:
        pass


def _run_jsx_file(app_name, jsx_path, timeout=120):
    """JSX 파일을 InDesign에서 실행."""
    # 한글 경로 회피: /tmp에 복사 (이미 /tmp이면 스킵)
    if jsx_path.startswith("/tmp/"):
        tmp_jsx = jsx_path
    else:
        tmp_jsx = f"/tmp/final_extract_{os.getpid()}.jsx"
        shutil.copy2(jsx_path, tmp_jsx)

    boot = (
        f'app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;'
        f'var _f = new File("{tmp_jsx}");'
        f'app.doScript(_f, ScriptLanguage.JAVASCRIPT);'
    )
    escaped = boot.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    script = f'tell application "{app_name}" to do script "{escaped}" language javascript'

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return True
        stderr = result.stderr.strip()
        # -609는 InDesign이 백그라운드에서 처리 중일 수 있음
        if "-609" in stderr:
            time.sleep(5)
            return True
        if "30486" in stderr:
            _dismiss_indesign_dialogs(app_name)
            time.sleep(3)
            return True
    except subprocess.TimeoutExpired:
        # 타임아웃이어도 InDesign이 처리 중일 수 있음
        time.sleep(5)
        return True

    return False


def _build_extract_jsx(indd_path, output_json_path, style_filters):
    """워크북에서 스타일 기반 텍스트 추출 JSX를 생성."""
    styles_js = json.dumps(style_filters, ensure_ascii=False)

    jsx = f"""#target indesign
app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;

var targetStyles = {styles_js};
var inddPath = "{indd_path.replace(chr(92), '/')}";
var outputPath = "{output_json_path.replace(chr(92), '/')}";

var doc;
try {{
    doc = app.open(File(inddPath), false);
}} catch(e) {{
    var ef = new File(outputPath);
    ef.open("w"); ef.encoding = "UTF-8";
    ef.write('{{"error":"' + e.message + '","stories":[]}}');
    ef.close();
    // exit
}}

if (doc) {{
    var results = [];

    // 강 페이지 맵 구축: 각 페이지에서 "Unit.N" 또는 "{{N강}}" 헤더 프레임 검색.
    // 우선순위: Unit.N (공용 올포 파일 간지) > {{N강}} (학교 워크북 마커)
    // 결과: lectureStartPages = [{{page: 2, num: 1}}, {{page: 14, num: 2}}, ...] (오름차순)
    var lectureStartPages = [];
    var unitPagesSeen = {{}};  // num -> minPageOff (first occurrence)
    var hasUnitMarkers = false;
    for (var lpi = 0; lpi < doc.pages.length; lpi++) {{
        var lpg = doc.pages[lpi];
        var lpgOff = lpg.documentOffset;
        var ltfs = lpg.textFrames;
        for (var lfi = 0; lfi < ltfs.length; lfi++) {{
            try {{
                var ltf = ltfs[lfi];
                var fullTxt = ltf.contents || "";
                // Unit.N 검색 (공용 올포 파일 간지 헤더 프레임에만 존재)
                var um = fullTxt.match(/Unit[\\.\\s]*(\\d+)/);
                if (um) {{
                    hasUnitMarkers = true;
                    var un = parseInt(um[1], 10);
                    // 각 Unit 번호의 첫 등장 페이지만 기록 (간지 페이지 = 최초 등장)
                    if (unitPagesSeen[un] === undefined || lpgOff < unitPagesSeen[un]) {{
                        unitPagesSeen[un] = lpgOff;
                    }}
                }}
            }} catch(e) {{}}
        }}
    }}
    if (hasUnitMarkers) {{
        // Unit.N 기반 구축
        for (var uk in unitPagesSeen) {{
            if (unitPagesSeen.hasOwnProperty(uk)) {{
                lectureStartPages.push({{page: unitPagesSeen[uk], num: parseInt(uk, 10)}});
            }}
        }}
    }} else {{
        // Fallback: {{N강}} 마커 검색
        for (var lpi2 = 0; lpi2 < doc.pages.length; lpi2++) {{
            var lpg2 = doc.pages[lpi2];
            var lpgOff2 = lpg2.documentOffset;
            var ltfs2 = lpg2.textFrames;
            for (var lfi2 = 0; lfi2 < ltfs2.length; lfi2++) {{
                try {{
                    var lt = ltfs2[lfi2].paragraphs[0].contents.replace(/[\\r\\n]/g, " ").replace(/\\s/g, "");
                    var lm = lt.match(/^\\{{(\\d+)강\\}}$/) || lt.match(/^(\\d+)강$/);
                    if (lm) {{
                        lectureStartPages.push({{page: lpgOff2, num: parseInt(lm[1], 10)}});
                        break;
                    }}
                }} catch(e) {{}}
            }}
        }}
    }}

    // pageOff로 lecture 번호 조회 (pageOff 이하 가장 큰 시작 페이지의 강)
    function _lectureOf(pgOff) {{
        if (pgOff < 0) return 0;
        var best = -1;
        var bestNum = 0;
        for (var k = 0; k < lectureStartPages.length; k++) {{
            var lsp = lectureStartPages[k];
            if (lsp.page <= pgOff && lsp.page > best) {{
                best = lsp.page;
                bestNum = lsp.num;
            }}
        }}
        return bestNum;
    }}

    // 모의고사 6자리 출처코드(YYMMQQ) 페이지 맵
    // 워크북에 한 번이라도 박혀있는 코드를 페이지별로 수집 → 가장 가까운 페이지의 코드를
    // 같은 블록의 다른 스토리에 부착하기 위함.
    // 매칭 규칙: 첫 단락이 정확히 6자리 숫자이거나 {{6자리}} / [6자리] / 6자리~2자리 형식.
    var examCodes = [];  // [{{page: pgOff, code: "YYMMQQ"}}, ...]
    for (var ecpi = 0; ecpi < doc.pages.length; ecpi++) {{
        var ecpg = doc.pages[ecpi];
        var ecOff = ecpg.documentOffset;
        var ecFrames = ecpg.textFrames;
        for (var ecfi = 0; ecfi < ecFrames.length; ecfi++) {{
            try {{
                var ecFirst = ecFrames[ecfi].paragraphs[0].contents
                    .replace(/[\\r\\n]/g, "")
                    .replace(/\\s/g, "");
                var ecClean = ecFirst.replace(/[\\{{\\}}\\[\\]]/g, "");
                // YYMMQQ 단독 또는 YYMMQQ~RR(범위 — 41~42 같은 복합문항).
                // 범위가 있으면 헤더로 통째 사용 (예: "230341~42").
                var ecm = ecClean.match(/^(\\d{{4}})(\\d{{2}})(?:[~\\-](\\d{{1,2}}))?$/);
                if (ecm) {{
                    var codeVal = ecm[1] + ecm[2];
                    if (ecm[3]) {{
                        var qq2 = (ecm[3].length === 1 ? "0" + ecm[3] : ecm[3]);
                        codeVal = ecm[1] + ecm[2] + "~" + qq2;
                    }}
                    examCodes.push({{page: ecOff, code: codeVal}});
                }}
            }} catch(eec) {{}}
        }}
    }}
    function _examCodeOf(pgOff) {{
        if (pgOff == null || pgOff < 0 || examCodes.length === 0) return "";
        var best = "";
        var bestDist = 99999;
        for (var eci = 0; eci < examCodes.length; eci++) {{
            var ec = examCodes[eci];
            var d = Math.abs(ec.page - pgOff);
            if (d < bestDist) {{ bestDist = d; best = ec.code; }}
        }}
        // 한 블록(=A~O 마스터 사이클 7스프레드 ≈ 14페이지) 범위 내 코드만 채택.
        if (bestDist > 7) return "";
        return best;
    }}

    // 페이지별 올포 레이블 맵: pageLabels[pgOff] = {{section: "문장 배열", label: "분석"|"01"|"02"|"03"|"논술"|"[분석]"|"[2]"|"[3]"}}
    // section: y≈-21 위치 프레임의 섹션명 (예: "문장 배열", "영작 배열", "빈칸 어휘")
    // label: y≈28~35 범위 작은 프레임의 번호 (예: "01", "02", "분석", "[분석]", "[2]", "논술")
    var pageLabels = {{}};
    function _trim(s) {{ return s.replace(/^\\s+|\\s+$/g, ""); }}
    for (var pli = 0; pli < doc.pages.length; pli++) {{
        var plPg = doc.pages[pli];
        var plOff = plPg.documentOffset;
        var plFrames = plPg.textFrames;
        var plSection = "";
        var plLabel = "";
        // 섹션명 후보 프레임 + 번호 후보 프레임 수집
        var labelCands = [];  // {{y, x, txt}}
        for (var plfi = 0; plfi < plFrames.length; plfi++) {{
            try {{
                var fr = plFrames[plfi];
                var bb = fr.geometricBounds;
                var fY = bb[0];
                var fX = bb[1];
                var firstTxt = _trim(fr.paragraphs[0].contents.replace(/[\\r\\n]+/g, "").replace(/\\t/g, ""));
                // 섹션명: y < 0 (예: y=-21), 텍스트에 "문장 배열"/"영작 배열"/"빈칸" 등
                if (fY < 0 && firstTxt.length > 0 && firstTxt.length < 30) {{
                    plSection = firstTxt.replace(/^\\s+/, "");
                }}
                // 레이블 후보: y가 0~40 범위, 짧은 텍스트
                if (fY >= -5 && fY < 40 && firstTxt.length < 10) {{
                    // 숫자 2자리, "분석", "[분석]", "[N]", "논술" 등
                    var clean = firstTxt.replace(/\\s/g, "").replace(/[│|]$/, "");
                    labelCands.push({{y: fY, x: fX, txt: clean}});
                }}
            }} catch(epl) {{}}
        }}
        // 우선순위: "분석" > "[분석]" > "01"/"02"/"03" > "[2]"/"[3]" > "논술" > "논술형"
        // 여러 후보 중 첫번째 선택 (페이지 하나에 여러 번호가 있는 경우 드묾)
        // 다만, 동일 페이지에 여러 번호가 있으면 pageLabels[pgOff]에 array로 저장
        var pageLblArr = [];
        for (var lci = 0; lci < labelCands.length; lci++) {{
            var lc = labelCands[lci];
            var txt = lc.txt;
            // 매칭되는 레이블
            if (/^\\d{{1,2}}$/.test(txt)) {{
                var nn = parseInt(txt, 10);
                if (nn >= 1 && nn <= 9) {{
                    pageLblArr.push({{y: lc.y, x: lc.x, raw: txt, kind: "num", val: nn}});
                }}
            }} else if (/^\\[\\d+\\]$/.test(txt)) {{
                pageLblArr.push({{y: lc.y, x: lc.x, raw: txt, kind: "bracket_num", val: parseInt(txt.replace(/[\\[\\]]/g, ""), 10)}});
            }} else if (txt === "\ubd84\uc11d" || txt === "[\ubd84\uc11d]") {{
                pageLblArr.push({{y: lc.y, x: lc.x, raw: txt, kind: "analyze"}});
            }} else if (txt === "\ub17c\uc220" || txt === "\ub17c\uc220\ud615") {{
                pageLblArr.push({{y: lc.y, x: lc.x, raw: txt, kind: "non"}});
            }} else if (txt === "\uc11c\uc220" || txt === "\uc11c\uc220\ud615") {{
                pageLblArr.push({{y: lc.y, x: lc.x, raw: txt, kind: "seo"}});
            }}
        }}
        pageLabels[plOff] = {{section: plSection, labels: pageLblArr}};
    }}

    // 스토리 첫 프레임의 페이지+y좌표로 올포 레이블 반환
    // "분석"/"[분석]" → "분석", "01" → "본문1", "02" → "본문2", "03" → "본문3",
    // "논술" → "논술형", "서술" → "서술형", "[2]" → "서술형", "[3]" → "논술형"
    function _olpoLabelOf(pgOff, storyY) {{
        var pl = pageLabels[pgOff];
        if (!pl || !pl.labels || pl.labels.length === 0) return "";
        // 같은 페이지에 여러 번호가 있으면 storyY에 가까운 번호 선택
        var best = null;
        var bestDist = 99999;
        for (var k = 0; k < pl.labels.length; k++) {{
            var lab = pl.labels[k];
            var dist = (storyY != null && storyY >= 0) ? Math.abs(lab.y - storyY) : 0;
            if (dist < bestDist) {{ bestDist = dist; best = lab; }}
        }}
        if (!best) return "";
        var sec = pl.section || "";
        // 영작 배열 섹션: [분석]→분석, [2]→서술형, [3]→논술형
        var isWriting = (sec.indexOf("\uc601\uc791") !== -1);
        if (best.kind === "analyze") return "\ubd84\uc11d";
        if (best.kind === "non") return "\ub17c\uc220\ud615";
        if (best.kind === "seo") return "\uc11c\uc220\ud615";
        if (best.kind === "bracket_num") {{
            // 영작 배열의 [2]/[3] → 서술형/논술형
            if (isWriting) {{
                if (best.val === 2) return "\uc11c\uc220\ud615";
                if (best.val === 3) return "\ub17c\uc220\ud615";
            }}
            return "\ubcf8\ubb38" + best.val;
        }}
        if (best.kind === "num") return "\ubcf8\ubb38" + best.val;
        return "";
    }}

    for (var si = 0; si < doc.stories.length; si++) {{
        var st = doc.stories[si];
        if (st.paragraphs.length < 2) continue;

        var storyParas = [];
        var hasTarget = false;

        for (var pi = 0; pi < st.paragraphs.length; pi++) {{
            var para = st.paragraphs[pi];
            var styleName = "";
            try {{ styleName = para.appliedParagraphStyle.name; }} catch(e) {{}}

            var txt = para.contents;
            if (txt) txt = txt.replace(/\\r$/, "");

            // 대상 스타일 포함 여부
            for (var ti = 0; ti < targetStyles.length; ti++) {{
                if (styleName === targetStyles[ti]) {{ hasTarget = true; break; }}
            }}

            storyParas.push({{
                s: styleName,
                t: txt
            }});
        }}

        if (hasTarget && storyParas.length > 0) {{
            // 프레임 페이지 오프셋 수집
            var tc = st.textContainers;
            var framePages = [];
            var hasPlacedFrame = false;
            for (var fpi = 0; fpi < tc.length; fpi++) {{
                try {{
                    if (tc[fpi].parentPage) {{
                        framePages.push(tc[fpi].parentPage.documentOffset);
                        hasPlacedFrame = true;
                    }} else {{
                        framePages.push(-1);
                    }}
                }} catch(e) {{ framePages.push(-1); }}
            }}

            // 어느 페이지에도 배치되지 않은 잔존 스토리는 제외
            if (!hasPlacedFrame) continue;

            // 빈칸어휘 스토리 감지: 한 프레임 = 한 본문 구조이므로 페이지 갭 조건을 완화
            var _isVocabStory = false;
            for (var _vpi = 0; _vpi < storyParas.length; _vpi++) {{
                var _vsn = storyParas[_vpi].s;
                if (_vsn === "C2_\ube48\uce78 \uc5b4\ud718" || _vsn === "C_\ube48\uce78 \uc5b4\ubc95 \ubc88\ud638") {{
                    _isVocabStory = true;
                    break;
                }}
            }}
            var _gapThr = _isVocabStory ? 0 : 2;
            var _minFrames = _isVocabStory ? 1 : 2;

            // 페이지 갭 감지: 프레임 간 페이지 차이 > 임계값이면 분할 지점
            var splitPoints = [0]; // 단락 인덱스 기준 분할 지점
            if (tc.length > _minFrames) {{
                var prevPage = framePages[0];
                var paraAccum = 0;
                for (var fpi2 = 0; fpi2 < tc.length; fpi2++) {{
                    if (fpi2 > 0 && framePages[fpi2] >= 0 && prevPage >= 0) {{
                        if (framePages[fpi2] - prevPage > _gapThr) {{
                            // 갭 발견 — 이 프레임부터 새 블록
                            // 현재 프레임의 첫 단락 인덱스 계산
                            var paraSoFar = 0;
                            for (var cfp = 0; cfp < fpi2; cfp++) {{
                                try {{ paraSoFar += tc[cfp].parentStory.textContainers[cfp].texts[0].paragraphs.length; }} catch(e) {{
                                    // 폴백: 프레임 텍스트 길이 기반 추정
                                    try {{ paraSoFar += tc[cfp].paragraphs.length; }} catch(e2) {{}}
                                }}
                            }}
                            if (paraSoFar > 0 && paraSoFar < storyParas.length) {{
                                splitPoints.push(paraSoFar);
                            }}
                        }}
                    }}
                    if (framePages[fpi2] >= 0) prevPage = framePages[fpi2];
                }}
            }}

            // 지문번호 읽기 함수 (storyY 기반 매칭)
            // 한 페이지에 여러 지문이 있는 경우(모의고사 상/하단 2개) storyY보다 작거나 같은(= 위 또는 같은 높이) 번호 중 가장 가까운 것 선택
            function _readPageQNum(thePage, storyY) {{
                if (!thePage) return "";
                try {{
                    var pgItems = thePage.textFrames;
                    var candidates = [];
                    for (var pfi = 0; pfi < pgItems.length; pfi++) {{
                        var firstLine = "";
                        var itemY = 99999;
                        try {{
                            firstLine = pgItems[pfi].paragraphs[0].contents.replace(/\\r$/, "").replace(/\\s/g, "");
                            itemY = pgItems[pfi].geometricBounds[0];
                        }} catch(e3) {{ continue; }}
                        var matched = null;
                        if (/^\\d{{6}}$/.test(firstLine)) matched = firstLine;
                        else {{
                            var numOnly = firstLine.replace(/[\\{{\\}}\\[\\]]/g, "");
                            if (/^\\d{{2}}$/.test(numOnly)) {{
                                var n = parseInt(numOnly, 10);
                                if (n >= 18 && n <= 45) matched = numOnly;
                            }} else {{
                                var rangeClean = firstLine.replace(/[\\{{\\}}\\[\\]]/g, "").replace("-", "~");
                                if (/^\\d{{2}}~\\d{{2}}$/.test(rangeClean)) matched = rangeClean;
                            }}
                        }}
                        if (matched) candidates.push({{y: itemY, v: matched}});
                    }}
                    if (candidates.length === 0) return "";
                    if (storyY == null || storyY < 0 || candidates.length === 1) return candidates[0].v;
                    // storyY 위쪽에 있는 번호 중 가장 가까운 것
                    var best = null;
                    var bestDist = 99999;
                    for (var ci = 0; ci < candidates.length; ci++) {{
                        var c = candidates[ci];
                        if (c.y <= storyY + 5) {{
                            var dist = storyY - c.y;
                            if (dist >= 0 && dist < bestDist) {{ bestDist = dist; best = c.v; }}
                        }}
                    }}
                    if (best) return best;
                    // fallback: 절대 거리 최소
                    var minDiff = 99999;
                    for (var ci2 = 0; ci2 < candidates.length; ci2++) {{
                        var diff = Math.abs(candidates[ci2].y - storyY);
                        if (diff < minDiff) {{ minDiff = diff; best = candidates[ci2].v; }}
                    }}
                    return best || "";
                }} catch(e2) {{}}
                return "";
            }}

            // 분할 지점이 1개(=분할 없음)면 기존 방식
            if (splitPoints.length <= 1) {{
                var pageOff = framePages.length > 0 ? framePages[0] : -1;
                var thePage = null;
                var storyY = -1;
                try {{ thePage = tc[0].parentPage; storyY = tc[0].geometricBounds[0]; }} catch(e) {{}}
                results.push({{
                    idx: si,
                    pageOff: pageOff,
                    pageQNum: _readPageQNum(thePage, storyY),
                    examCode: _examCodeOf(pageOff),
                    lecture: _lectureOf(pageOff),
                    olpoLabel: _olpoLabelOf(pageOff, storyY),
                    paras: storyParas
                }});
            }} else {{
                // 분할 지점으로 블록 나누기
                splitPoints.push(storyParas.length);
                var splitFrameIdx = 0;
                for (var spi = 0; spi < splitPoints.length - 1; spi++) {{
                    var from = splitPoints[spi];
                    var to = splitPoints[spi + 1];
                    var subParas = storyParas.slice(from, to);
                    // 해당 분할의 첫 프레임 페이지
                    var spPage = null;
                    var spOff = -1;
                    var spY = -1;
                    // splitFrameIdx 추적: from 이상의 단락을 포함하는 프레임
                    while (splitFrameIdx < tc.length) {{
                        try {{ spPage = tc[splitFrameIdx].parentPage; spOff = spPage.documentOffset; spY = tc[splitFrameIdx].geometricBounds[0]; }} catch(e) {{}}
                        break;
                    }}
                    results.push({{
                        idx: si,
                        pageOff: spOff,
                        pageQNum: _readPageQNum(spPage, spY),
                        examCode: _examCodeOf(spOff),
                        lecture: _lectureOf(spOff),
                        olpoLabel: _olpoLabelOf(spOff, spY),
                        paras: subParas
                    }});
                    // 다음 분할의 프레임 시작점 이동
                    for (var nfp = splitFrameIdx; nfp < tc.length; nfp++) {{
                        if (framePages[nfp] >= 0 && framePages[nfp] > framePages[splitFrameIdx] + 1) {{
                            splitFrameIdx = nfp;
                            break;
                        }}
                    }}
                }}
            }}
        }}
    }}

    // JSON 저장
    var outFile = new File(outputPath);
    outFile.open("w");
    outFile.encoding = "UTF-8";

    // ES3 JSON 직렬화
    var jsonStr = '[';
    for (var ri = 0; ri < results.length; ri++) {{
        if (ri > 0) jsonStr += ',';
        var pqn = results[ri].pageQNum || "";
        var pqnEsc = pqn.replace(/"/g, '\\\\"');
        var ecVal = results[ri].examCode || "";
        var ecEsc = ecVal.replace(/"/g, '\\\\"');
        var lec = results[ri].lecture || 0;
        var olpoLbl = results[ri].olpoLabel || "";
        var olpoLblEsc = olpoLbl.replace(/"/g, '\\\\"');
        jsonStr += '{{"idx":' + results[ri].idx + ',"pageOff":' + results[ri].pageOff + ',"pageQNum":"' + pqnEsc + '","examCode":"' + ecEsc + '","lecture":' + lec + ',"olpoLabel":"' + olpoLblEsc + '","paras":[';
        var pp = results[ri].paras;
        for (var ppi = 0; ppi < pp.length; ppi++) {{
            if (ppi > 0) jsonStr += ',';
            // 텍스트 이스케이프
            var escaped = pp[ppi].t || "";
            escaped = escaped.replace(/\\\\/g, "\\\\\\\\");
            escaped = escaped.replace(/"/g, '\\\\"');
            escaped = escaped.replace(/\\n/g, "\\\\n");
            escaped = escaped.replace(/\\t/g, "\\\\t");
            var sEsc = pp[ppi].s || "";
            sEsc = sEsc.replace(/"/g, '\\\\"');
            jsonStr += '{{"s":"' + sEsc + '","t":"' + escaped + '"}}';
        }}
        jsonStr += ']}}';
    }}
    jsonStr += ']';

    outFile.write(jsonStr);
    outFile.close();

    doc.close(SaveOptions.NO);
}}
"""
    return jsx


def extract_from_workbooks(indd_paths, style_filters, output_path, log):
    """여러 워크북 .indd에서 텍스트를 추출하여 통합 JSON 생성.

    Args:
        indd_paths: 워크북 .indd 파일 경로 리스트
        style_filters: 추출할 단락 스타일명 리스트
        output_path: 결과 JSON 저장 경로
        log: 로그 콜백 함수
    """
    app_name = _find_app()
    log(f"[추출] InDesign: {app_name}")

    # InDesign 초기화
    _dismiss_indesign_dialogs(app_name)
    # 작업 중인 다른 문서 보호: 전체 문서 닫기(close-all) 제거.
    # 추출용 임시 복사본은 각 추출 종료 시 doc.close로 개별 정리됨.

    all_stories = []

    for i, indd_path in enumerate(indd_paths):
        basename = os.path.basename(indd_path)
        log(f"[추출] ({i+1}/{len(indd_paths)}) {basename}")

        # 한글 경로 회피: /tmp에 복사 (워크북마다 다른 경로로 deadlock 회피)
        # Google Drive Stream FS는 fcopyfile/read syscall에서 EBUSY/EDEADLK 반환 →
        # _gdrive_safe_copy는 python rw → cat → dd → cp 다단계 폴백 + 지수 백오프 재시도.
        tmp_indd = f"/tmp/final_wb_{os.getpid()}_{i}.indd"
        copied, last_err = _gdrive_safe_copy(indd_path, tmp_indd, log=log)
        if not copied:
            # GDrive에서 워크북을 못 가져오면 해당 워크북 데이터가 통째로 누락되므로 즉시 중단.
            msg = f"GDrive 워크북 복사 실패 (재시도 초과): {basename} — 마지막 오류: {last_err}"
            log(f"  [오류] {msg}")
            raise RuntimeError(msg)

        # 추출 결과 경로
        tmp_result = f"/tmp/final_extract_result_{os.getpid()}.json"
        if os.path.exists(tmp_result):
            os.remove(tmp_result)

        # JSX 생성 및 실행
        jsx_code = _build_extract_jsx(tmp_indd, tmp_result, style_filters)
        jsx_path = f"/tmp/final_extract_{os.getpid()}.jsx"
        with open(jsx_path, "w", encoding="utf-8") as f:
            f.write(jsx_code)

        success = _run_jsx_file(app_name, jsx_path, timeout=120)

        # 결과 대기 (로그 파일 폴링 방식)
        waited = 0
        while not os.path.exists(tmp_result) and waited < 60:
            time.sleep(2)
            waited += 2

        if os.path.exists(tmp_result):
            try:
                with open(tmp_result, encoding="utf-8") as f:
                    _txt = f.read()
                try:
                    stories = json.loads(_txt)
                except json.JSONDecodeError:
                    # InDesign 특수/제어문자가 escape 안 된 채 JSON에 섞여 표준 파싱 실패.
                    # 관대 모드(strict=False)로 재시도 — 워크북 전체 스토리 통째 누락 방지
                    # (예: 성덕1 워크북02 모의고사 문장배열/영작 통째 손실 사고).
                    stories = json.loads(_txt, strict=False)
                    log("  JSON strict=False 재파싱 성공 (제어문자 포함)")
                if isinstance(stories, dict) and stories.get("error"):
                    log(f"  추출 에러: {stories['error']}")
                elif isinstance(stories, list):
                    log(f"  {len(stories)}개 스토리 추출")
                    for st in stories:
                        st["source_file"] = basename
                    all_stories.extend(stories)
            except Exception as e:
                log(f"  JSON 파싱 실패: {e}")
        else:
            log(f"  추출 결과 없음 (타임아웃)")

        # 임시 파일 정리
        for tmp in [tmp_indd, tmp_result, jsx_path]:
            try:
                os.remove(tmp)
            except Exception:
                pass

    # 통합 JSON 저장
    result = {
        "workbook_count": len(indd_paths),
        "story_count": len(all_stories),
        "stories": all_stories
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log(f"[추출] 완료: {len(all_stories)}개 스토리 → {os.path.basename(output_path)}")
    return output_path


def _build_mock_insert_extract_jsx(indd_path, output_json_path, allowed_qnums):
    """모의고사 통합 파일에서 '문장삽입' 블록만 추출하는 JSX 생성.

    판정: 발문 "아래 주어진 문장이 들어갈 곳으로 적당한 곳을 고르시오"를 포함하는
    스토리만 채택한다. 각 스토리는 (문항번호, 주어진 문장, 본문 + 번호 선택지)를 담는다.
    """
    qnums_js = json.dumps(list(allowed_qnums), ensure_ascii=False)

    jsx = f"""#target indesign
app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;

var allowedQnums = {qnums_js};
var inddPath = "{indd_path.replace(chr(92), '/')}";
var outputPath = "{output_json_path.replace(chr(92), '/')}";

function inAllowed(qn) {{
    if (!allowedQnums || allowedQnums.length === 0) return true;
    for (var i = 0; i < allowedQnums.length; i++) {{
        if (allowedQnums[i] === qn) return true;
    }}
    // qn이 "41~42" 같은 범위면 내부 각 번호가 허용되는지 체크
    var rm = qn.match(/^(\\d+)[~\\-](\\d+)$/);
    if (rm) {{
        var a = parseInt(rm[1], 10);
        var b = parseInt(rm[2], 10);
        for (var j = a; j <= b; j++) {{
            for (var k = 0; k < allowedQnums.length; k++) {{
                if (allowedQnums[k] === String(j)) return true;
            }}
        }}
    }}
    return false;
}}

var doc;
try {{
    doc = app.open(File(inddPath), false);
}} catch(e) {{
    var ef = new File(outputPath);
    ef.open("w"); ef.encoding = "UTF-8";
    ef.write('{{"error":"' + e.message + '","stories":[]}}');
    ef.close();
}}

if (doc) {{
    var results = [];
    // 문장삽입 발문: "아래 주어진 문장이 들어갈 곳으로..."
    // 순서배열 발문: "아래 주어진 문장 다음에 이어질..."
    // 두 유형 모두 파이널 "문장 삽입/순서 배열" 섹션에 포함됨
    var INSERT_PROMPT_1 = "\uc544\ub798 \uc8fc\uc5b4\uc9c4 \ubb38\uc7a5\uc774 \ub4e4\uc5b4\uac08";
    var INSERT_PROMPT_2 = "\uc544\ub798 \uc8fc\uc5b4\uc9c4 \ubb38\uc7a5 \ub2e4\uc74c\uc5d0 \uc774\uc5b4\uc9c8";
    // 추가 변형: "글의 흐름으로 보아, 주어진 문장이 들어가기에"
    var INSERT_PROMPT_3 = "\uc8fc\uc5b4\uc9c4 \ubb38\uc7a5\uc774 \ub4e4\uc5b4\uac00\uae30\uc5d0";

    function isQnumLine(cleanTxt) {{
        var cn = cleanTxt.replace(/\\s/g, "");
        // plain digits: 20
        if (/^\\d{{1,2}}$/.test(cn)) {{
            var n = parseInt(cn, 10);
            if (n >= 18 && n <= 45) return cn;
        }}
        // plain range: 41~42, 41-42
        if (/^\\d{{1,2}}[~\\-]\\d{{1,2}}$/.test(cn)) {{
            return cn.replace("-", "~");
        }}
        // braced: {{20}}, [20]
        var bm = cn.match(/^[\\{{\\[](\\d{{1,2}})[\\}}\\]]$/);
        if (bm) {{
            var bn = parseInt(bm[1], 10);
            if (bn >= 18 && bn <= 45) return bm[1];
        }}
        // braced range: {{41~42}}, [41~42], {{41-42}}
        var bm2 = cn.match(/^[\\{{\\[](\\d{{1,2}}[~\\-]\\d{{1,2}})[\\}}\\]]$/);
        if (bm2) {{
            return bm2[1].replace("-", "~");
        }}
        // 연속 마커 변형: {{41}}{{~42}}, {{41}}{{-42}}, [41][~42]
        var bm2b = cn.match(/^[\\{{\\[](\\d{{1,2}})[\\}}\\]][\\{{\\[][~\\-](\\d{{1,2}})[\\}}\\]]$/);
        if (bm2b) {{
            return bm2b[1] + "~" + bm2b[2];
        }}
        // 교과서 본문N: {{본문1}}, [본문1], {{Read More}}
        var bm3 = cn.match(/^[\\{{\\[](\ubcf8\ubb38\\d+)[\\}}\\]]$/);
        if (bm3) return bm3[1];
        // Read More → "RM" (미래엔 등), Further Reading → "FR" (YBM 등)
        var bm4r = cn.match(/^[\\{{\\[]Read\\s*More[\\}}\\]]$/i);
        if (bm4r) return "RM";
        var bm4f = cn.match(/^[\\{{\\[]Further\\s*Reading[\\}}\\]]$/i);
        if (bm4f) return "FR";
        return "";
    }}

    function emitSegment(segParas, segQnum, originIdx) {{
        if (!segQnum) return;
        // 세그먼트 내 INSERT_PROMPT 위치 찾기
        var promptIdx = -1;
        for (var ii = 0; ii < segParas.length; ii++) {{
            var cc = (segParas[ii].t || "").replace(/[\\r\\n\\t]/g, " ").replace(/^\\s+|\\s+$/g, "");
            if (cc.indexOf(INSERT_PROMPT_1) !== -1 ||
                cc.indexOf(INSERT_PROMPT_2) !== -1 ||
                cc.indexOf(INSERT_PROMPT_3) !== -1) {{
                promptIdx = ii;
                break;
            }}
        }}
        if (promptIdx < 0) return;  // INSERT_PROMPT 없음 → 문장삽입 아님
        if (!inAllowed(segQnum)) return;
        // 문항번호 헤더 + INSERT_PROMPT 이후 paras만 유지 (그 앞의 문장배열 내용 제외)
        var filtered = [];
        if (segParas.length > 0) filtered.push(segParas[0]);  // qnum header
        for (var kk = promptIdx; kk < segParas.length; kk++) {{
            filtered.push(segParas[kk]);
        }}
        results.push({{idx: originIdx, qnum: segQnum, paras: filtered}});
    }}

    for (var si = 0; si < doc.stories.length; si++) {{
        var st = doc.stories[si];
        if (st.paragraphs.length < 3) continue;

        // 한 스토리 내에 여러 문항번호가 연이어 있을 수 있음 (threaded).
        // "[기본 단락]" 스타일이면서 문항번호로 보이는 줄(18~45)이 나오면 세그먼트 분리.
        var segParas = [];
        var segQnum = "";

        for (var pi = 0; pi < st.paragraphs.length; pi++) {{
            var para = st.paragraphs[pi];
            var styleName = "";
            try {{ styleName = para.appliedParagraphStyle.name; }} catch(e) {{}}

            var txt = para.contents;
            if (txt) txt = txt.replace(/\\r$/, "");
            var cleanTxt = (txt || "").replace(/[\\r\\n\\t]/g, " ").replace(/^\\s+|\\s+$/g, "");

            var isBasic = (styleName === "[\\uAE30\\uBCF8 \\uB2E8\\ub77d]" || styleName === "[Basic Paragraph]" ||
                           styleName === "[\uae30\ubcf8 \ub2e8\ub77d]");
            var detectedQnum = isBasic ? isQnumLine(cleanTxt) : "";

            if (detectedQnum) {{
                // 이전 세그먼트 종료
                if (segParas.length > 0) emitSegment(segParas, segQnum, si);
                segParas = [];
                segQnum = detectedQnum;
                // 문항번호 단락 자체도 세그먼트에 포함 (문항번호 기록용)
                segParas.push({{s: styleName, t: txt || ""}});
                continue;
            }}

            segParas.push({{s: styleName, t: txt || ""}});
        }}

        // 마지막 세그먼트 flush
        if (segParas.length > 0) emitSegment(segParas, segQnum, si);
    }}

    var outFile = new File(outputPath);
    outFile.open("w");
    outFile.encoding = "UTF-8";

    var jsonStr = '[';
    for (var ri = 0; ri < results.length; ri++) {{
        if (ri > 0) jsonStr += ',';
        jsonStr += '{{"idx":' + results[ri].idx + ',"qnum":"' + results[ri].qnum + '","paras":[';
        var pp = results[ri].paras;
        for (var ppi = 0; ppi < pp.length; ppi++) {{
            if (ppi > 0) jsonStr += ',';
            var escaped = pp[ppi].t || "";
            escaped = escaped.replace(/\\\\/g, "\\\\\\\\");
            escaped = escaped.replace(/"/g, '\\\\"');
            escaped = escaped.replace(/\\n/g, "\\\\n");
            escaped = escaped.replace(/\\r/g, "\\\\r");
            escaped = escaped.replace(/\\t/g, "\\\\t");
            var sEsc = pp[ppi].s || "";
            sEsc = sEsc.replace(/"/g, '\\\\"');
            jsonStr += '{{"s":"' + sEsc + '","t":"' + escaped + '"}}';
        }}
        jsonStr += ']}}';
    }}
    jsonStr += ']';

    outFile.write(jsonStr);
    outFile.close();

    doc.close(SaveOptions.NO);
}}
"""
    return jsx


def extract_mock_insert_blocks(indd_path, allowed_qnums, log):
    """모의고사 통합 워크북 파일에서 문장삽입 블록만 추출.

    Args:
        indd_path: 통합 워크북 .indd 경로
        allowed_qnums: 허용할 문항번호 set (예: {"38", "39"}). 빈 set이면 전체.
        log: 로그 콜백
    Returns:
        [{"qnum": "38", "paras": [{"s":..., "t":...}, ...]}, ...]
    """
    app_name = _find_app()
    log(f"[문장삽입 추출] {os.path.basename(indd_path)}")
    basename = os.path.basename(indd_path)

    # /tmp로 복사 — fcopyfile 우회용 헬퍼 사용 (GDrive Resource busy 회피)
    tmp_indd = f"/tmp/final_mock_insert_{os.getpid()}.indd"
    copied, last_err = _gdrive_safe_copy(indd_path, tmp_indd, log=log)
    if not copied:
        # GDrive 모의고사 통합 워크북 복사 실패 시 데이터 누락 방지를 위해 즉시 중단.
        msg = (f"GDrive 모의고사 문장삽입 워크북 복사 실패 (5회 재시도): "
               f"{basename} — 마지막 오류: {last_err}")
        log(f"  [오류] {msg}")
        raise RuntimeError(msg)

    tmp_result = f"/tmp/final_mock_insert_result_{os.getpid()}.json"
    if os.path.exists(tmp_result):
        os.remove(tmp_result)

    jsx_code = _build_mock_insert_extract_jsx(tmp_indd, tmp_result, list(allowed_qnums))
    jsx_path = f"/tmp/final_mock_insert_{os.getpid()}.jsx"
    with open(jsx_path, "w", encoding="utf-8") as f:
        f.write(jsx_code)

    _run_jsx_file(app_name, jsx_path, timeout=180)

    waited = 0
    while not os.path.exists(tmp_result) and waited < 120:
        time.sleep(2)
        waited += 2

    results = []
    if os.path.exists(tmp_result):
        try:
            with open(tmp_result, encoding="utf-8") as f:
                _rtxt = f.read()
            try:
                results = json.loads(_rtxt)
            except json.JSONDecodeError:
                # InDesign 제어문자 escape 누락 대비 관대 파싱(strict=False)
                results = json.loads(_rtxt, strict=False)
                log("  [문장삽입 추출] JSON strict=False 재파싱 성공")
            if isinstance(results, dict) and results.get("error"):
                log(f"  [문장삽입 추출] 에러: {results['error']}")
                results = []
            elif isinstance(results, list):
                log(f"  [문장삽입 추출] {len(results)}개 블록 추출")
                for r in results:
                    r["source_file"] = basename
        except Exception as e:
            log(f"  [문장삽입 추출] JSON 파싱 실패: {e}")

    for tmp in [tmp_indd, tmp_result, jsx_path]:
        try:
            os.remove(tmp)
        except Exception:
            pass

    return results
