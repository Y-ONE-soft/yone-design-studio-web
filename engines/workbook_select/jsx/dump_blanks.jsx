// [ENGINE TEMPLATE] 빈칸 섹션 문단 덤프 (검수용) — 읽기 전용
//
// 빈칸어휘/빈칸어법의 지문별·문장별 빈칸 개수를 원고와 대조하기 위한 원시
// 데이터. 산출물의 빈칸 표기는 경로에 따라 다르다:
//   원고 기반 조판 : "160[m    ]"  (텍스트 공백)
//   완성본 재사용  : "160[m￼]"     (앵커 도형)
// 둘 다 세야 하므로 텍스트를 그대로 덤프하고 판정은 파이썬이 한다.
//
// 대상 문서는 열려 있으면 그것을, 아니면 __INDD_PATH__ 를 연다.
#target indesign
(function () {
    var INDD = "__INDD_PATH__";
    var OUT = "__OUT_PATH__";

    var doc = null, openedByUs = false, i, j, k;
    for (i = 0; i < app.documents.length; i++) {
        try {
            if (String(app.documents[i].fullName) == String(new File(INDD))) {
                doc = app.documents[i]; break;
            }
        } catch (e) {}
    }
    // ☠ "문서가 하나뿐이면 그것을 쓴다" 폴백 금지 — 한글 경로는 NFD/NFC 가
    //    갈려 위 비교가 자주 실패하는데, 그때 **다른 세션/사용자가 열어둔 남의
    //    문서**를 대상으로 삼는다. 실측 2026-08-17: 검수 시점에 열려 있던
    //    '한영2_분석본01' 을 덤프해 빈칸 0건([])이 나왔고, 그 빈 결과가
    //    타임아웃으로 이어져 **빈칸 대조가 통째로 건너뛰어졌다**.
    //    이름(파일명)으로 한 번 더 찾고, 그래도 없으면 경로로 연다
    //    (이미 열려 있으면 app.open 이 그 문서 참조를 돌려준다).
    if (doc === null) {
        var wantName = String(new File(INDD).name);
        for (i = 0; i < app.documents.length; i++) {
            try {
                if (String(app.documents[i].name) == wantName) {
                    doc = app.documents[i]; break;
                }
            } catch (e) {}
        }
    }
    if (doc === null) {
        doc = app.open(new File(INDD), false);
        openedByUs = true;
    }

    function esc(s) {
        s = String(s);
        var o = "", c;
        for (var x = 0; x < s.length; x++) {
            c = s.charAt(x);
            if (c === '"') { o += '\\"'; }
            else if (c === "\\") { o += "\\\\"; }
            else if (c === "\r" || c === "\n") { o += " "; }
            else if (c < " ") { o += " "; }
            else { o += c; }
        }
        return o;
    }

    // 러닝 라벨로 섹션 판별 (프레임 y<0 인 짧은 라벨)
    function sectionOf(pg) {
        var tfs = pg.textFrames, s = "";
        for (var t = 0; t < tfs.length; t++) {
            try {
                var gb = tfs[t].geometricBounds;
                if (gb[0] > 10) continue;
                var c = String(tfs[t].contents).replace(/[\r\n]/g, " ");
                if (c.length < 30 && c.replace(/\s/g, "").length > 0) {
                    s = c.replace(/^\s+|\s+$/g, "");
                }
            } catch (e) {}
        }
        return s;
    }

    // 러닝 라벨은 한쪽 페이지에만 있는 경우가 있다 — 마지막 값을 이어서 쓴다.
    // (이 처리가 없으면 홀수 페이지가 통째로 검사에서 빠져 20문항 중 9개만
    //  대조됐다 — 2026-08-13 실측)
    var out = [];
    var lastSec = "";
    for (i = 0; i < doc.pages.length; i++) {
        var pg = doc.pages[i];
        var sec = sectionOf(pg);
        if (sec.replace(/\s/g, "") !== "") { lastSec = sec; }
        else { sec = lastSec; }
        if (sec.indexOf("빈칸") < 0) { continue; }
        // 지문번호 = 본문 밖 짧은 숫자 프레임
        var label = "";
        var tfs = pg.textFrames;
        for (j = 0; j < tfs.length; j++) {
            try {
                var c0 = String(tfs[j].contents).replace(/[\r\n\s]/g, "");
                if (/^\d{1,3}$/.test(c0)) { label = c0; }
            } catch (e) {}
        }
        for (j = 0; j < tfs.length; j++) {
            var ps;
            try { ps = tfs[j].paragraphs; } catch (e) { continue; }
            if (ps.length < 3) { continue; }          // 본문 프레임만
            for (k = 0; k < ps.length; k++) {
                var t;
                try { t = String(ps[k].contents); } catch (e) { continue; }
                t = t.replace(/[\r\n]+$/, "");
                if (t === "") { continue; }
                out.push('{"page":"' + esc(pg.name) + '","section":"'
                         + esc(sec) + '","label":"' + esc(label)
                         + '","idx":' + k + ',"text":"' + esc(t) + '"}');
            }
        }
    }

    var f = new File(OUT);
    f.encoding = "UTF-8"; f.lineFeed = "Unix";
    f.open("w");
    f.write("[" + out.join(",\n") + "]");
    f.close();
    if (openedByUs) { doc.close(SaveOptions.NO); }
})();
