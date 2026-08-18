// [ENGINE TEMPLATE] 세로→가로 후처리: 미사용 슬롯 페이지 제거
//
// 가로 템플릿은 지문 슬롯을 넉넉히 갖고 있어, 선택한 문항 수가 적으면
// **마스터 장식만 있고 내용이 없는 페이지**가 그대로 남는다
// (2026-08-18 실측: 16문항 변환 시 283p 중 64p 가 빈 슬롯).
//
// ⚠ workbook_select 의 trim_pages.jsx 를 그대로 쓰면 안 된다. 그쪽은
//   "스레드(multi-container) 스토리"를 내용 판정 기준으로 삼는데, v2h 산출물은
//   지문마다 **단일 프레임 스토리**라 전 페이지가 "내용 없음"으로 판정된다.
//
// 유지 규칙:
//   - 마스터 없음([None]) = 표지/간지/앞부속 → 무조건 유지
//   - M-마스터 = 파리티 패딩용 메모 페이지 → 유지 (지우면 좌우가 밀린다)
//   - 로컬 텍스트프레임에 실내용(공백·앵커기호 제외 30자+) 있으면 유지
#target indesign
(function () {
    var settingsPath = "__SETTINGS_PATH__";
    var logFile = new File(settingsPath.replace(/\.settings\.json$/, "trim_로그.txt"));
    logFile.encoding = "UTF-8"; logFile.lineFeed = "Unix";
    function W(s) { logFile.open("a"); logFile.writeln(s); logFile.close(); }
    W("미사용 슬롯 정리 시작");

    var d = null;
    try {
        var sf = new File(settingsPath);
        sf.encoding = "UTF-8"; sf.open("r");
        var settings = eval("(" + sf.read() + ")");
        sf.close();

        d = app.open(new File(settings.indd_path), false);
        try { d.adjustLayoutPreferences.enableAdjustLayout = false; } catch (e0) {}

        var before = d.pages.length, removed = 0, scanned = 0;
        for (var i = d.pages.length - 1; i >= 0; i--) {
            scanned++;
            if (scanned % 50 === 0) { W("스캔 " + scanned + "p..."); }
            var pg = d.pages[i], mn = "";
            try { mn = pg.appliedMaster ? pg.appliedMaster.name : ""; } catch (e1) {}
            if (mn === "" || mn === "[None]") { continue; }      // 표지/간지
            if (mn.indexOf("M-") === 0) { continue; }            // 파리티 패딩

            var hasContent = false, tfs = pg.textFrames;
            for (var t = 0; t < tfs.length; t++) {
                var c = "";
                try { c = String(tfs[t].contents); } catch (e2) { continue; }
                c = c.replace(/[\r\n\s￼]/g, "");
                if (c.length >= 30) { hasContent = true; break; }
            }
            if (!hasContent) {
                try { pg.remove(); removed++; } catch (e3) {
                    W("[경고] p" + pg.name + " 삭제 실패: " + e3);
                }
            }
        }
        W("미사용 슬롯 삭제: " + removed + "개 / " + before + "p → " + d.pages.length + "p");

        // 삭제 후 내용이 사라지지 않았는지 확인 (침묵 금지)
        var ov = 0, chars = 0;
        for (var s2 = 0; s2 < d.stories.length; s2++) {
            if (d.stories[s2].overflows) { ov++; }
            chars += d.stories[s2].characters.length;
        }
        W("[검수] 잔여 오버셋 " + ov + "개 / 전체 문자 " + chars + "자");
        if (removed > 0) { d.save(); W("저장 완료"); }
        W("===== 정리 완료 =====");
    } catch (eM) {
        W("[오류] " + (eM.message || eM));
        W("===== 정리 완료 =====");
    }
    try { if (d && d.isValid) { d.close(SaveOptions.NO); } } catch (eC) {}
})();
