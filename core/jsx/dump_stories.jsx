// 조판 결과 덤프 — 완성 .indd의 스토리별 (단락 텍스트, 적용 단락스타일)을 JSON으로.
// 검수 게이트(core/inspect)의 입력. ExtendScript ES3 — let/const/템플릿 리터럴 금지.
// 플레이스홀더 __INDD_PATH__/__OUT_PATH__/__LOG_PATH__ 는 파이썬 러너가 치환.
// 문서는 읽기 전용으로 열고(SaveOptions.NO로 닫음) 아무것도 수정하지 않는다.

var INDD = "__INDD_PATH__";
var OUT = "__OUT_PATH__";
var LOG = "__LOG_PATH__";
var settingsPath = "__LOG_PATH__";  // core.indesign.runner 호환용 (러너가 존재만 검사 — 미사용)

function wlog(msg) {
    var f = new File(LOG);
    f.encoding = "UTF-8";
    f.open("a");
    f.writeln(msg);
    f.close();
}

function esc(s) {
    s = String(s);
    var out = "";
    for (var i = 0; i < s.length; i++) {
        var c = s.charAt(i);
        var n = s.charCodeAt(i);
        if (c == "\\") { out += "\\\\"; }
        else if (c == "\"") { out += "\\\""; }
        else if (n == 10) { out += "\\n"; }
        else if (n == 13) { out += "\\r"; }
        else if (n == 9) { out += "\\t"; }
        else if (n < 32) { out += " "; }
        else if (n < 127) { out += c; }
        else {
            // 비ASCII 전부 \uXXXX 이스케이프 — ExtendScript File.write가
            // 외자 서러게이트 등에서 조용히 실패(0바이트 파일)하는 문제 회피
            var hex = n.toString(16);
            while (hex.length < 4) { hex = "0" + hex; }
            out += "\\u" + hex;
        }
    }
    return out;
}

function styleFullName(st) {
    try {
        var name = st.name;
        var par = st.parent;
        if (par && par.constructor && par.constructor.name == "ParagraphStyleGroup") {
            return par.name + " > " + name;
        }
        return name;
    } catch (e) { return ""; }
}

var doc = null;
try {
    wlog("덤프 시작: " + INDD);
    doc = app.open(File(INDD), false);   // showingWindow=false — 사용자 화면 방해 X
    var stories = doc.stories.everyItem().getElements();
    var buf = [];
    buf.push("{\"doc\":\"" + esc(doc.name) + "\",\"stories\":[");
    var overflowCount = 0;
    for (var si = 0; si < stories.length; si++) {
        var st = stories[si];
        // 벌크 게터 — 단락별 개별 DOM 접근은 대형 문서에서 수 분 걸림.
        // everyItem() 일괄 호출은 단락 1개일 때 스칼라를 반환하므로 배열화.
        var texts = [];
        var styles = [];
        try {
            texts = st.paragraphs.everyItem().contents;
            styles = st.paragraphs.everyItem().appliedParagraphStyle;
            if (!(texts instanceof Array)) { texts = [texts]; }
            if (!(styles instanceof Array)) { styles = [styles]; }
        } catch (e) { texts = []; styles = []; }
        var sb = [];
        for (var pi = 0; pi < texts.length; pi++) {
            var txt = texts[pi];
            if (typeof txt != "string") { txt = String(txt); }
            var sty = "";
            try { sty = styleFullName(styles[pi]); } catch (e) {}
            sb.push("{\"t\":\"" + esc(txt) + "\",\"s\":\"" + esc(sty) + "\"}");
        }
        if (si % 10 == 0) {   // 하트비트 — 러너 행 감지(5분 무갱신) 방지
            wlog("진행: 스토리 " + (si + 1) + "/" + stories.length);
        }
        var ovf = false;
        try {
            var tc = st.textContainers;
            ovf = tc.length > 0 && tc[tc.length - 1].overflows;
        } catch (e) {}
        if (ovf) { overflowCount++; }
        buf.push((si > 0 ? "," : "") + "{\"idx\":" + si + ",\"overflow\":" +
                 (ovf ? "true" : "false") + ",\"paragraphs\":[" + sb.join(",") + "]}");
    }
    buf.push("],\"overflow_stories\":" + overflowCount + "}");
    var out = new File(OUT);
    out.encoding = "UTF-8";
    if (!out.open("w")) { throw "OUT open 실패: " + OUT; }
    var payload = buf.join("");
    var okWrite = out.write(payload);
    out.close();
    var written = new File(OUT).length;
    wlog("쓰기: write=" + okWrite + " bytes=" + written + "/" + payload.length);
    if (!okWrite || written <= 0) { throw "OUT write 실패 (bytes=" + written + ")"; }
    doc.close(SaveOptions.NO);
    doc = null;
    wlog("덤프 완료: 스토리 " + stories.length + "개, 오버플로우 스토리 " + overflowCount + "개");
} catch (e) {
    wlog("[오류] " + e);
    try { if (doc) { doc.close(SaveOptions.NO); } } catch (e2) {}
}
