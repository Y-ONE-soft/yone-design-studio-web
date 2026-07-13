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
        // W11 additive 필드: pg = 프레임이 놓인 페이지 이름들(순서), b = 첫
        // 프레임 [top,left] (상/하단 배치 검수용). 기존 소비자는 추가 키 무시.
        // W21 additive 필드: fc = 각 텍스트 프레임 첫 문자의 스토리 내 문자
        // 인덱스 (빈 프레임은 -1) — 게이트 G24(프레임 브레이크 실측)용.
        var pgs = [];
        var b0 = null;
        var fcs = [];
        try {
            var tc2 = st.textContainers;
            var seenPg = {};
            for (var ti = 0; ti < tc2.length; ti++) {
                var ppg = null;
                try { ppg = tc2[ti].parentPage; } catch (e) {}
                var fci = -1;
                try {
                    if (tc2[ti].characters.length > 0) {
                        fci = tc2[ti].characters[0].index;
                    }
                } catch (e) {}
                fcs.push(String(fci));
                if (!ppg) { continue; }
                var pnm = String(ppg.name);
                if (!seenPg[pnm]) { seenPg[pnm] = true; pgs.push("\"" + esc(pnm) + "\""); }
                if (b0 === null) {
                    var gb0 = tc2[ti].geometricBounds;
                    b0 = "[" + Math.round(gb0[0]) + "," + Math.round(gb0[1]) + "]";
                }
            }
        } catch (e) {}
        buf.push((si > 0 ? "," : "") + "{\"idx\":" + si + ",\"overflow\":" +
                 (ovf ? "true" : "false") +
                 ",\"pg\":[" + pgs.join(",") + "]" +
                 ",\"fc\":[" + fcs.join(",") + "]" +
                 (b0 !== null ? ",\"b\":" + b0 : "") +
                 ",\"paragraphs\":[" + sb.join(",") + "]}");
    }
    // W11: 잔여 사이클 페이지 검출 — 다중 프레임 스토리(=사이클 본문) 프레임이
    // 있는데 전부 빈 페이지 (지문번호/발문 등 단일 프레임 장식만 남은 페이지).
    var stale = [];
    try {
        var allPgs = doc.pages.everyItem().getElements();
        for (var spi = 0; spi < allPgs.length; spi++) {
            var stfs = allPgs[spi].textFrames;
            var hasLocal = false;
            var allBlank = true;
            for (var sfi = 0; sfi < stfs.length; sfi++) {
                var multi = false;
                try { multi = stfs[sfi].parentStory.textContainers.length > 1; } catch (e) {}
                if (!multi) { continue; }
                hasLocal = true;
                var cc = "";
                try { cc = String(stfs[sfi].contents || ""); } catch (e) {}
                if (cc.replace(/[\s\r\n￼]+/g, "").length > 0) { allBlank = false; break; }
            }
            if (hasLocal && allBlank) {
                var mnm = "";
                try { mnm = allPgs[spi].appliedMaster ? String(allPgs[spi].appliedMaster.name) : ""; } catch (e) {}
                stale.push("{\"p\":\"" + esc(String(allPgs[spi].name)) +
                           "\",\"m\":\"" + esc(mnm) + "\"}");
            }
        }
    } catch (e) {}
    // W21 additive: 전체 페이지 인벤토리 — 이름/마스터/좌우/빈 페이지 여부.
    // 게이트 G26(섹션 시작 좌/우 마스터 변형)·전체-1(빈 페이지 잔존) 실측용.
    var pagesInfo = [];
    try {
        var invPgs = doc.pages.everyItem().getElements();
        for (var ipi = 0; ipi < invPgs.length; ipi++) {
            var ipg = invPgs[ipi];
            var im = "";
            try { im = ipg.appliedMaster ? String(ipg.appliedMaster.name) : ""; } catch (e) {}
            // 비대면(facing 아님) 문서는 pg.side가 전부 RIGHT_HAND — 인쇄
            // 물리 좌/우는 페이지 순서 홀짝으로 판정 (offset 0 = p1 = 오른쪽).
            var iside = "";
            try {
                var facing = false;
                try { facing = doc.documentPreferences.facingPages; } catch (e) {}
                if (facing) {
                    iside = (ipg.side === PageSideOptions.LEFT_HAND) ? "L" : "R";
                } else {
                    iside = (ipg.documentOffset % 2 === 0) ? "R" : "L";
                }
            } catch (e) {}
            var itfs = ipg.textFrames;
            var iEmpty = true;
            for (var itf = 0; itf < itfs.length; itf++) {
                var icc = "";
                try { icc = String(itfs[itf].contents || ""); } catch (e) {}
                if (icc.replace(/[\s\r\n￼]+/g, "").length > 0) { iEmpty = false; break; }
            }
            if (itfs.length === 0) { iEmpty = false; }   // 프레임 없는 표지류는 '빈 페이지' 아님
            pagesInfo.push("{\"p\":\"" + esc(String(ipg.name)) +
                           "\",\"m\":\"" + esc(im) +
                           "\",\"side\":\"" + iside +
                           "\",\"empty\":" + (iEmpty ? "true" : "false") + "}");
        }
    } catch (e) {}
    buf.push("],\"overflow_stories\":" + overflowCount +
             ",\"page_count\":" + doc.pages.length +
             ",\"pages\":[" + pagesInfo.join(",") + "]" +
             ",\"stale_pages\":[" + stale.join(",") + "]}");
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
