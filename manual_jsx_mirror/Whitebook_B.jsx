// Whitebook_B.jsx
// 112P~ 답지: ▶X(정답지 번호) → 정답_ + 뱃지 / [문제N]+빈줄 → 해설_
(function () {
    var doc = app.activeDocument;

    function findParaStyle(name) {
        var all = doc.allParagraphStyles;
        for (var i = 0; i < all.length; i++) {
            if (all[i].name === name) return all[i];
        }
        return null;
    }

    var styleAnswer  = findParaStyle("\uC815\uB2F5_");    // 정답_
    var styleSection = findParaStyle("\uD574\uC124_");    // 해설_

    if (!styleAnswer)  { alert("'\uC815\uB2F5_' \uC2A4\uD0C0\uC77C\uC744 \uCC3E\uC744 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4."); return; }
    if (!styleSection) { alert("'\uD574\uC124_' \uC2A4\uD0C0\uC77C\uC744 \uCC3E\uC744 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4."); return; }

    // 뱃지 색상 (참조 페이지 66-67 실측값)
    var colorMap = {
        "A": "C=65 M=36 Y=22 K=0",
        "B": "C=19 M=42 Y=56 K=0",
        "C": "C=52 M=27 Y=39 K=9",
        "D": "C=20 M=41 Y=10 K=0",
        "E": "C=44 M=43 Y=52 K=0"
    };

    var paperSwatch = doc.swatches.itemByName("Paper");

    // 66페이지 참조 뱃지에서 폰트 취득
    var badgeFont = null;
    try {
        var rItems = doc.pages[65].allPageItems;
        for (var ri = 0; ri < rItems.length; ri++) {
            try {
                if (rItems[ri].parent.constructor.name === "Character") {
                    badgeFont = rItems[ri].texts[0].characters[0].appliedFont;
                    break;
                }
            } catch(e) {}
        }
    } catch(e) {}

    var startIdx = 111; // 112페이지 (0-based)
    var changed = 0;

    for (var pi = startIdx; pi < doc.pages.length; pi++) {
        var pg = doc.pages[pi];
        for (var fi = 0; fi < pg.textFrames.length; fi++) {
            var fr = pg.textFrames[fi];
            var paras = fr.texts[0].paragraphs;

            for (var i = 0; i < paras.length; i++) {
                var para = paras[i];
                if (para.appliedParagraphStyle.name !== "\uC815\uB2F5\uC9C0 \uBC88\uD638") continue;

                var txt = para.contents.replace(/\r$/, "");

                if (txt.charAt(0) === "\u25B6" && txt.length >= 3) {
                    // ▶ X → 정답_ + 색상 뱃지
                    var letter = txt.charAt(2);
                    var cname  = colorMap[letter];
                    if (!cname) continue;
                    var bColor = doc.swatches.itemByName(cname);
                    if (!bColor || !bColor.isValid) continue;

                    // 내용: 공백 + 정답 + 공백 (뱃지 삽입 후 " ￼ 정답 " 형태)
                    para.texts[0].contents = "  \uC815\uB2F5 ";
                    para = fr.texts[0].paragraphs[i];

                    // 삽입점 1에 인라인 텍스트 프레임 추가
                    var ip = para.insertionPoints[1];
                    var bf = ip.textFrames.add(
                        doc.layers[0],
                        LocationOptions.UNKNOWN,
                        { geometricBounds: [0, 0, 6.3, 6.3],
                          fillColor: bColor,
                          strokeWeight: 1 }
                    );
                    bf.texts[0].contents = letter;
                    if (badgeFont) {
                        var bch = bf.texts[0].characters[0];
                        bch.appliedFont = badgeFont;
                        bch.pointSize   = 12;
                        bch.fillColor   = paperSwatch;
                    }

                    // 단락 스타일 적용
                    para = fr.texts[0].paragraphs[i];
                    para.appliedParagraphStyle = styleAnswer;
                    changed++;

                } else if (txt.indexOf("[\uBB38\uC81C") === 0) {
                    // [문제 N] → 해설_
                    para.appliedParagraphStyle = styleSection;
                    changed++;

                } else if (txt.replace(/\s/g, "") === "") {
                    // 빈 단락 → 해설_
                    para.appliedParagraphStyle = styleSection;
                    changed++;
                }
            }
        }
    }

    return "\uC644\uB8CC: " + changed + "\uAC1C \uB2E8\uB77D \uCC98\uB9AC\n"
         + "(\u25B6 \u2192 \uC815\uB2F5_ + \uBB38\uC790 \uBC31\uC9C0 / [\uBB38\uC81C]\uC640 \uBE48\uC904 \u2192 \uD574\uC124_)";
})();
