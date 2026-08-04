// [ENGINE TEMPLATE] 워크북 선택 결합 — 후처리: 미사용 페이지 제거 + 간지 텍스트
// 선택 조판은 문항 수가 템플릿 용량(18문항)보다 적어, 섹션마다 미사용
// 페이지가 남는다. 미사용 페이지에는 템플릿 유래 정적 잔재(발문 보일러
// 플레이트, 낡은 지문번호 라벨)가 있어 run.jsx 16.5(전 프레임 빈 페이지만
// 삭제)가 잡지 못한다 — 여기서는 "스레드(multi-container) 스토리 프레임에
// 내용이 있는가"만 본다. 정적 라벨(단일 프레임 스토리)은 장식으로 간주.
//
// 유지 규칙:
//   - 마스터 없음([None]) 페이지 = 앞부속/간지 → 무조건 유지
//   - 스레드 스토리 프레임에 실내용(공백·앵커기호 U+FFFC 제외) 있으면 유지
// 간지 텍스트: 1페이지형 간지(단일 TF, 2단락+, 한글)의 2단락을
//   settings.divider_line2 로 교체 (기본 "" — 회차 혼합본에서 "23년 11월"
//   같은 첫 코드 회차 오표기 방지).
#target indesign
(function () {
    var settingsPath = "__SETTINGS_PATH__";

    // 로그를 가장 먼저 연다 — 러너의 전달 확인/스톨 감지가 이 파일의
    // 갱신을 하트비트로 삼는다 (긴 removal 루프 중 무갱신이면 600초
    // 스톨 오탐으로 작업이 보류됨 — 2026-08-04 실측).
    var logFile = new File(settingsPath.replace(/\.settings\.json$/,
                                                "trim_로그.txt"));
    logFile.encoding = "UTF-8";
    logFile.lineFeed = "Unix";
    function W(s) { logFile.open("a"); logFile.writeln(s); logFile.close(); }
    W("trim 시작");

    try {
        var sf = new File(settingsPath);
        sf.encoding = "UTF-8";
        sf.open("r");
        var settings = eval("(" + sf.read() + ")");
        sf.close();

        var d = app.open(new File(settings.indd_path), false);
        try { d.adjustLayoutPreferences.enableAdjustLayout = false; } catch (e0) {}

        var removed = 0;
        var scanned = 0;
        for (var i = d.pages.length - 1; i >= 0; i--) {
            scanned++;
            if (scanned % 40 === 0) W("스캔 " + scanned + "p...");
            var pg = d.pages[i];
            var mn = "";
            try { mn = pg.appliedMaster ? pg.appliedMaster.name : ""; } catch (e1) {}
            if (mn === "" || mn === "[None]") continue;   // 앞부속/간지

            var hasContent = false;
            var tfs = pg.textFrames;
            for (var t = 0; t < tfs.length; t++) {
                var st = null;
                try { st = tfs[t].parentStory; } catch (e2) { continue; }
                if (!st || st.textContainers.length <= 1) continue;  // 정적 라벨
                var c = "";
                try { c = tfs[t].contents || ""; } catch (e3) {}
                if (typeof c !== "string") c = String(c);
                c = c.replace(/[\s\r\n\uFFFC]+/g, "");
                if (c.length > 0) { hasContent = true; break; }
            }
            if (!hasContent) {
                try { pg.remove(); removed++; } catch (e4) {}
            }
        }
        W("미사용 페이지 삭제: " + removed + "개 / 잔여 " + d.pages.length + "p");

        // 간지 2단락(회차 표기) 교체
        var line2 = (settings.divider_line2 !== undefined)
            ? settings.divider_line2 : "";
        var fixed = 0;
        for (var p2 = 0; p2 < d.pages.length; p2++) {
            var dpg = d.pages[p2];
            var mn2 = "";
            try { mn2 = dpg.appliedMaster ? dpg.appliedMaster.name : ""; } catch (e5) {}
            if (mn2 !== "" && mn2 !== "[None]") continue;
            if (dpg.textFrames.length !== 1) continue;
            var tf2 = dpg.textFrames[0];
            var paras = tf2.paragraphs;
            if (paras.length < 2) continue;
            var p1txt = "";
            try { p1txt = paras[0].contents || ""; } catch (e6) {}
            if (!/[가-힣]/.test(String(p1txt))) continue;
            try {
                var last = paras[1].characters.length;
                if (last > 0) {
                    // 마지막 \r 는 남기고 내용만 교체
                    var endIdx = last;
                    try {
                        if (paras[1].characters[-1].contents === "\r") endIdx = last - 1;
                    } catch (e7) {}
                    if (endIdx > 0) {
                        paras[1].characters.itemByRange(0, endIdx - 1).contents = line2 || " ";
                    }
                    fixed++;
                }
            } catch (e8) {}
        }
        W("간지 2단락 교체: " + fixed + "곳 → \"" + line2 + "\"");

        d.save();
        d.close(SaveOptions.NO);
        W("===== trim 완료 =====");
    } catch (eMain) {
        W("[오류] " + (eMain.message || eMain));
    }
})();
