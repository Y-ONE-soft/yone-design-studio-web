// DeleteEmptyParas.jsx — 빈 단락 삭제 (다음 단락 스타일 보존)
// ※ 삭제 시 다음 단락이 빈 단락 스타일로 덮이는 문제를 방지하기 위해
//   "다음 비어있지 않은 단락"의 스타일을 미리 저장 후 복원함
#target "InDesign"

(function () {
    var doc = app.activeDocument;
    var totalDeleted = 0;
    var stories = doc.stories;

    for (var si = 0; si < stories.length; si++) {
        try {
            var story = stories[si];
            if (!story || !story.isValid) continue;
            try { if (!story.textContainers || story.textContainers.length === 0) continue; } catch (e) { continue; }
            totalDeleted += deleteEmptyFrom(story);
        } catch (e) {}
    }

    alert("빈 단락 " + totalDeleted + "개 삭제 완료\n(단락 스타일 보존)");

    // ── 다음 비어있지 않은 단락의 스타일 반환 ──────────
    function nextNonEmptyStyle(paras, fromIdx) {
        for (var j = fromIdx + 1; j < paras.length; j++) {
            try {
                var c = (paras[j].contents || "").replace(/\r$/, "");
                if (!/^\s*$/.test(c)) return paras[j].appliedParagraphStyle;
            } catch (e) {}
        }
        return null;
    }

    // ── 스토리 내 빈 단락 삭제 (10패스 반복) ───────────
    function deleteEmptyFrom(story) {
        var deleted = 0;

        for (var pass = 0; pass < 10; pass++) {
            // 현재 단락 배열 스냅샷
            var paras = story.paragraphs.everyItem().getElements();
            var n = paras.length;

            // 빈 단락 수집 — 높은 인덱스 순(역순)으로 정렬
            var toDelete = [];
            for (var i = n - 2; i >= 0; i--) {   // 마지막 단락(스토리 종결자)은 제외
                try {
                    var content = (paras[i].contents || "").replace(/\r$/, "");
                    if (!/^\s*$/.test(content)) continue;
                    // 다음 비어있지 않은 단락의 스타일 미리 저장
                    var ns = nextNonEmptyStyle(paras, i);
                    toDelete.push({ idx: i, style: ns });
                } catch (e) {}
            }

            if (toDelete.length === 0) break;   // 빈 단락 없음 → 종료

            // 높은 인덱스부터 삭제 (낮은 인덱스는 영향받지 않음)
            for (var di = 0; di < toDelete.length; di++) {
                try {
                    var item = toDelete[di];
                    var p = story.paragraphs[item.idx];
                    if (!p || !p.isValid) continue;

                    // 여전히 비어있는지 재확인
                    var c2 = (p.contents || "").replace(/\r$/, "");
                    if (!/^\s*$/.test(c2)) continue;

                    // 단락 문자 전체(포함 \r) 삭제
                    var chars = p.characters;
                    if (!chars || chars.length === 0) continue;
                    story.characters.itemByRange(
                        chars[0].index,
                        chars[chars.length - 1].index
                    ).remove();

                    // 삭제로 인해 합쳐진 단락에 저장해 둔 스타일 복원
                    if (item.style) {
                        try { story.paragraphs[item.idx].appliedParagraphStyle = item.style; } catch (e) {}
                    }
                    deleted++;
                } catch (e) {}
            }
        }

        return deleted;
    }
})();
