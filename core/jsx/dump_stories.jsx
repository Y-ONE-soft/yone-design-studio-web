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
        // W40 additive: cx = 탭 포함 단락의 첫 라인 셀 시작 수평 오프셋
        // (탭 뒤 문자 horizontalOffset, mm 아님 — 문서 좌표계 그대로.
        // 게이트 G42가 다열 선지 열 정렬 실측에 사용). 탭 단락에만 개별
        // DOM 접근 — 대량 벌크 게터 경로는 무변경.
        var paraEls = null;
        var sb = [];
        for (var pi = 0; pi < texts.length; pi++) {
            var txt = texts[pi];
            if (typeof txt != "string") { txt = String(txt); }
            var sty = "";
            try { sty = styleFullName(styles[pi]); } catch (e) {}
            var cxj = "";
            if (txt.indexOf("\t") >= 0 && txt.length < 200) {
                try {
                    if (paraEls === null) {
                        paraEls = st.paragraphs.everyItem().getElements();
                    }
                    var pObj = paraEls[pi];
                    var cells = [];
                    var chs = pObj.characters;
                    cells.push(String(Math.round(chs[0].horizontalOffset * 100) / 100));
                    for (var cxi = 0; cxi < txt.length - 1 && cxi < 150; cxi++) {
                        if (txt.charAt(cxi) == "\t") {
                            cells.push(String(Math.round(chs[cxi + 1].horizontalOffset * 100) / 100));
                        }
                    }
                    cxj = ",\"cx\":[" + cells.join(",") + "]";
                } catch (e) { cxj = ""; }
            }
            sb.push("{\"t\":\"" + esc(txt) + "\",\"s\":\"" + esc(sty) + "\"" + cxj + "}");
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
        var fps = [];
        var fbs = [];
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
                // W23 additive: fp = 프레임별 페이지 이름 (fc와 병렬 —
                // 게이트 G30이 단락→페이지 실측에 사용. 페이지 밖은 "").
                fps.push("\"" + esc(ppg ? String(ppg.name) : "") + "\"");
                // W29 additive: fb = 프레임별 geometricBounds [t,l,b,r]
                // (fp와 병렬 — 시각 검수의 겹침/경계 이탈 검출용. 실패는 null).
                var fbj = "null";
                try {
                    var gbF = tc2[ti].geometricBounds;
                    fbj = "[" + Math.round(gbF[0] * 100) / 100 + "," +
                          Math.round(gbF[1] * 100) / 100 + "," +
                          Math.round(gbF[2] * 100) / 100 + "," +
                          Math.round(gbF[3] * 100) / 100 + "]";
                } catch (e) {}
                fbs.push(fbj);
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
                 ",\"fp\":[" + fps.join(",") + "]" +
                 ",\"fb\":[" + fbs.join(",") + "]" +
                 (b0 !== null ? ",\"b\":" + b0 : "") +
                 ",\"paragraphs\":[" + sb.join(",") + "]}");
    }
    // W40 additive: hox = 프레임 오른쪽 경계를 벗어난 라인 실측 (밑줄
    // 빈칸 런 "_{6,}" 포함 라인 한정 — findGrep 1회, 게이트 G43 입력).
    // 라인 끝 수평 오프셋 > 프레임 우측 내변(geometricBounds - inset)이면
    // 기록. 문서 좌표계(mm) 그대로 — fb와 동일 기준.
    var hoxBuf = [];
    try {
        app.findGrepPreferences = NothingEnum.NOTHING;
        app.findGrepPreferences.findWhat = "_{6,}";
        var hits = doc.findGrep();
        var stIdById = {};
        for (var hsi = 0; hsi < stories.length; hsi++) {
            try { stIdById[stories[hsi].id] = hsi; } catch (e) {}
        }
        for (var hi = 0; hi < hits.length && hoxBuf.length < 200; hi++) {
            var hLine = null, hFrame = null;
            try { hLine = hits[hi].lines[0]; } catch (e) { continue; }
            if (!hLine) { continue; }
            try { hFrame = hLine.parentTextFrames[0]; } catch (e) {}
            if (!hFrame) { continue; }
            var endX = null, rimX = null;
            try { endX = hLine.endHorizontalOffset; } catch (e) {}
            try {
                var hgb = hFrame.geometricBounds;
                var rIn = 0;
                try {
                    var ins = hFrame.textFramePreferences.insetSpacing;
                    rIn = (ins instanceof Array) ? ins[3] : ins;
                } catch (e) {}
                rimX = hgb[3] - rIn;
            } catch (e) {}
            if (endX === null || rimX === null) { continue; }
            if (endX <= rimX + 0.2) { continue; }
            var hPg = "";
            try { hPg = String(hFrame.parentPage.name); } catch (e) {}
            var hSt = -1;
            try { hSt = stIdById[hits[hi].parentStory.id]; } catch (e) {}
            if (hSt === undefined) { hSt = -1; }
            var hTxt = "";
            try { hTxt = String(hLine.contents).substr(0, 40); } catch (e) {}
            hoxBuf.push("{\"st\":" + hSt + ",\"p\":\"" + esc(hPg) +
                        "\",\"over\":" + (Math.round((endX - rimX) * 100) / 100) +
                        ",\"t\":\"" + esc(hTxt) + "\"}");
        }
        app.findGrepPreferences = NothingEnum.NOTHING;
    } catch (e) {
        try { app.findGrepPreferences = NothingEnum.NOTHING; } catch (e2) {}
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
            // W29 additive: b = 페이지 bounds [t,l,b,r] (시각 검수 지오메트리 기준)
            var ipb = "null";
            try {
                var gbP = ipg.bounds;
                ipb = "[" + Math.round(gbP[0] * 100) / 100 + "," +
                      Math.round(gbP[1] * 100) / 100 + "," +
                      Math.round(gbP[2] * 100) / 100 + "," +
                      Math.round(gbP[3] * 100) / 100 + "]";
            } catch (e) {}
            pagesInfo.push("{\"p\":\"" + esc(String(ipg.name)) +
                           "\",\"m\":\"" + esc(im) +
                           "\",\"side\":\"" + iside +
                           "\",\"b\":" + ipb +
                           ",\"empty\":" + (iEmpty ? "true" : "false") + "}");
        }
    } catch (e) {}
    // W23 additive: 폰트 인벤토리 — 게이트 G29(글리프 커버리지)가 폰트
    // 파일(location)의 cmap을 실측하는 데 쓴다. fonts = 문서 사용 폰트
    // (name은 "패밀리\t스타일"), style_fonts = 단락스타일별 적용 폰트.
    var fontsInfo = [];
    try {
        var dfs = doc.fonts.everyItem().getElements();
        for (var dfi = 0; dfi < dfs.length; dfi++) {
            var fnm = "", floc = "", fst = "";
            try { fnm = String(dfs[dfi].name); } catch (e) {}
            try {
                floc = dfs[dfi].location ? String(dfs[dfi].location) : "";
            } catch (e) {}
            try { fst = String(dfs[dfi].status); } catch (e) {}
            fontsInfo.push("{\"n\":\"" + esc(fnm) + "\",\"loc\":\"" +
                           esc(floc) + "\",\"st\":\"" + esc(fst) + "\"}");
        }
    } catch (e) {}
    var styleFonts = [];
    try {
        var aps = doc.allParagraphStyles;
        for (var api = 0; api < aps.length; api++) {
            var sfull = "", sfam = "", ssty = "";
            try { sfull = styleFullName(aps[api]); } catch (e) {}
            if (!sfull) { continue; }
            try {
                var af = aps[api].appliedFont;
                sfam = (typeof af == "string") ? af : String(af.fontFamily);
            } catch (e) {}
            try { ssty = String(aps[api].fontStyle); } catch (e) {}
            styleFonts.push("{\"s\":\"" + esc(sfull) + "\",\"f\":\"" +
                            esc(sfam) + "\",\"fs\":\"" + esc(ssty) + "\"}");
        }
    } catch (e) {}
    buf.push("],\"overflow_stories\":" + overflowCount +
             ",\"page_count\":" + doc.pages.length +
             ",\"pages\":[" + pagesInfo.join(",") + "]" +
             ",\"fonts\":[" + fontsInfo.join(",") + "]" +
             ",\"style_fonts\":[" + styleFonts.join(",") + "]" +
             ",\"hox\":[" + hoxBuf.join(",") + "]" +
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
