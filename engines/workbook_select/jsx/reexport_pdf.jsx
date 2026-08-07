// [ENGINE TEMPLATE] 워크북 선택 결합 — trim 후 PDF 재출력
// run.jsx 가 PDF 를 먼저 export 하고, 그 뒤 trim_pages.jsx 가 미사용 페이지를
// 지우고 .indd 를 저장한다. 그래서 재출력하지 않으면 PDF 만 trim 이전 상태로
// 남는다 (2026-08-08 실측: INDD 292p vs PDF 310p — 빈 페이지 18개가 PDF 에만
// 그대로 남아 그대로 인쇄로 넘어갈 뻔했다).
#target indesign
(function () {
    var settingsPath = "__SETTINGS_PATH__";

    // 로그 최우선 생성 — 러너의 전달 확인/스톨 감지 하트비트
    var logFile = new File(settingsPath.replace(/\.settings\.json$/,
                                                "reexport_로그.txt"));
    logFile.encoding = "UTF-8";
    logFile.lineFeed = "Unix";
    function W(s) { logFile.open("a"); logFile.writeln(s); logFile.close(); }
    W("재출력 시작");

    try {
        var sf = new File(settingsPath);
        sf.encoding = "UTF-8";
        sf.open("r");
        var settings = eval("(" + sf.read() + ")");
        sf.close();

        var d = app.open(new File(settings.indd_path), false);
        W("문서: " + d.name + " / " + d.pages.length + "p");

        var preset = null;
        var names = ["[고품질 인쇄]", "[High Quality Print]",
                     "[프레스 품질]", "[Press Quality]"];
        for (var i = 0; i < names.length; i++) {
            try {
                var p = app.pdfExportPresets.itemByName(names[i]);
                if (p.isValid) { preset = p; break; }
            } catch (e1) {}
        }
        // pageRange 잔존값이 남으면 일부 페이지만 나온다 — 반드시 명시
        app.pdfExportPreferences.pageRange = PageRange.ALL_PAGES;
        W("PDF export 시작 (로그 무갱신 수 분 가능) / 프리셋 "
          + (preset ? preset.name : "기본"));
        if (preset) {
            d.exportFile(ExportFormat.PDF_TYPE, new File(settings.pdf_path),
                         false, preset);
        } else {
            d.exportFile(ExportFormat.PDF_TYPE, new File(settings.pdf_path),
                         false);
        }
        W("PDF 페이지 기대치: " + d.pages.length);
        d.close(SaveOptions.NO);
        W("===== 재출력 완료 =====");
    } catch (eMain) {
        W("[오류] " + (eMain.message || eMain));
    }
})();
