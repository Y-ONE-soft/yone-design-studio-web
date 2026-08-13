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
    // 한글 경로는 NFD/NFC 가 갈려 비교가 실패한다 — 문서가 하나뿐이면 그것을 쓴다
    if (doc === null && app.documents.length === 1) { doc = app.documents[0]; }
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

    var out = [];
    for (i = 0; i < doc.pages.length; i++) {
        var pg = doc.pages[i];
        var sec = sectionOf(pg);
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
