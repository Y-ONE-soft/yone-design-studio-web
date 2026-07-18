// 시각 검수용 페이지 PNG export — PDF가 없는 흐름(.indd만)의 렌더 경로.
// core.visual_inspect.render_indd_pages 가 플레이스홀더를 치환해 실행.
// 문서는 읽기 전용으로 열고(SaveOptions.NO) 아무것도 수정하지 않는다.
// ExtendScript ES3 — let/const/템플릿 리터럴 금지. 경로는 전부 절대경로.

var INDD = "__INDD_PATH__";
var OUT_DIR = "__OUT_DIR__";
var LOG = "__LOG_PATH__";
var DPI = __DPI__;
var settingsPath = "__LOG_PATH__";  // core.indesign.runner 호환용 (존재만 검사)

function wlog(msg) {
    var f = new File(LOG);
    f.encoding = "UTF-8";
    f.open("a");
    f.writeln(msg);
    f.close();
}

function pad4(n) {
    var s = String(n);
    while (s.length < 4) { s = "0" + s; }
    return s;
}

var doc = null;
try {
    wlog("PNG export 시작: " + INDD + " @ " + DPI + "dpi");
    var prevInteraction = null;
    try {
        prevInteraction = app.scriptPreferences.userInteractionLevel;
        app.scriptPreferences.userInteractionLevel =
            UserInteractionLevels.NEVER_INTERACT;
    } catch (e) {}
    doc = app.open(File(INDD), false);   // showingWindow=false — 사용자 화면 무접촉
    var outFolder = new Folder(OUT_DIR);
    if (!outFolder.exists) { outFolder.create(); }
    try { app.pngExportPreferences.exportResolution = DPI; } catch (e) {}
    try { app.pngExportPreferences.antiAlias = true; } catch (e) {}
    try { app.pngExportPreferences.transparentBackground = false; } catch (e) {}
    try { app.pngExportPreferences.exportingSpread = false; } catch (e) {}
    try {
        app.pngExportPreferences.pngColorSpace = PNGColorSpaceEnum.RGB;
    } catch (e) {}
    try {
        app.pngExportPreferences.pngQuality = PNGQualityEnum.MEDIUM;
    } catch (e) {}
    var total = doc.pages.length;
    for (var i = 0; i < total; i++) {
        // pageString "+N" = 문서 절대 순번 (섹션 번호 중복과 무관)
        try {
            app.pngExportPreferences.pngExportRange = PNGExportRangeEnum.EXPORT_RANGE;
        } catch (e) {}
        app.pngExportPreferences.pageString = "+" + (i + 1);
        var outFile = new File(OUT_DIR + "/page-" + pad4(i + 1) + ".png");
        doc.exportFile(ExportFormat.PNG_FORMAT, outFile);
        if (i % 10 == 0) {   // 하트비트 — 러너 행 감지(무갱신) 방지
            wlog("진행: 페이지 " + (i + 1) + "/" + total);
        }
    }
    doc.close(SaveOptions.NO);
    doc = null;
    try {
        if (prevInteraction !== null) {
            app.scriptPreferences.userInteractionLevel = prevInteraction;
        }
    } catch (e) {}
    wlog("PNG 내보내기 완료: " + total + "페이지");
} catch (e) {
    wlog("[오류] " + e);
    try { if (doc) { doc.close(SaveOptions.NO); } } catch (e2) {}
}
