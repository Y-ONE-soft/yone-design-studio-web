/* ===== InDesign ExtendScript (.jsx) =====
   형광펜_노랑(지문분석 폴더) 포함 문장마다
   "문장의 첫 번째 형광펜 단어 위"에 스크립트레이블 서술형아이콘 1개 삽입
*/
(function () {
    if (app.documents.length === 0) { alert("문서 없음"); return; }
    var doc = app.activeDocument;

    var GROUP_CS   = "지문분석";
    var STYLE_CS   = "형광펜_노랑";
    var ICON_LABEL_PRIMARY   = "서술형아이콘";

    var NUDGE_DX = 20;  
    var NUDGE_DY = -1;  
    var YoffsetPT = -3;    
    var XoffsetPT = 4;     

    function findLabeledItem(label){
        var items = doc.allPageItems, it;
        for (var ii=0; ii<items.length; ii++){
            it = items[ii];
            try { if (it.label === label) return it; } catch(_){}
        }
        return null;
    }
    function getCharStyle(groupName, styleName){
        try{
            var g = doc.characterStyleGroups.itemByName(groupName);
            if (g && g.isValid){
                var s = g.characterStyles.itemByName(styleName);
                if (s && s.isValid) return s;
            }
        }catch(_){}
        return null;
    }
    function safeResetFindChange(){
        app.findGrepPreferences    = NothingEnum.NOTHING;
        app.changeGrepPreferences  = NothingEnum.NOTHING;
        app.findTextPreferences    = NothingEnum.NOTHING;
        app.changeTextPreferences  = NothingEnum.NOTHING;
    }
    function adjustExistingIcons(dx, dy){
        var count = 0;
        try{
            var items = doc.allPageItems, it;
            for (var ii=0; ii<items.length; ii++){
                it = items[ii];
                try{
                    if (!(it && it.isValid && it.label === ICON_LABEL_PRIMARY)) continue;
                    try{ if (it.itemLayer){ it.itemLayer.locked = false; it.itemLayer.visible = true; } }catch(__){}
                    try{ it.locked = false; }catch(__){}
                    try{
                        var aos = it.anchoredObjectSettings;
                        if (aos){
                            try{ aos.horizontalReferencePoint = AnchoredRelativeTo.ANCHOR_LOCATION; }catch(__){}
                            try{ aos.verticalReferencePoint   = AnchoredRelativeTo.ANCHOR_LOCATION; }catch(__){}
                            try{ aos.lockPosition = false; }catch(__){}
                            if (aos.anchoredPosition !== AnchorPosition.ANCHORED){
                                aos.anchoredPosition = AnchorPosition.ANCHORED;
                            }
                            try{ aos.anchorPoint = AnchorPoint.BOTTOM_CENTER_ANCHOR; }catch(__){}
                            try{ aos.anchorXoffset = (aos.anchorXoffset || 0) + dx; }catch(__){}
                            try{ aos.anchorYoffset = (aos.anchorYoffset || 0) + dy; }catch(__){}
                            count++;
                            try{ clampIconToTextFrame(it, it.insertionPoints[0], 1); }catch(__){}
                            try{ clampIconToAnchorPage(it, it.insertionPoints[0], 1); }catch(__){}
                            try{ if (it.parentStory && it.parentStory.recompose) it.parentStory.recompose(); }catch(__){}
                            try{ it.bringToFront(); }catch(__){}
                        }
                    }catch(__){}
                }catch(__){}
            }
        }catch(_){}
        return count;
    }

    function clampIconToTextFrame(obj, ip, pad){
        try{
            var tf = (ip.parentTextFrames && ip.parentTextFrames.length) ? ip.parentTextFrames[0] : null;
            if (!tf || !tf.isValid) return;
            var aos = obj.anchoredObjectSettings;
            if (!aos) return;
            var gbF = tf.geometricBounds; 
            var left  = gbF[1] + pad;
            var right = gbF[3] - pad;
            var gbO = obj.geometricBounds; 
            var halfW = (gbO[3] - gbO[1]) / 2.0;
            var ipX = ip.horizontalOffset;
            var minOff = (left  + halfW) - ipX;
            var maxOff = (right - halfW) - ipX;
            var cur = (aos.anchorXoffset || 0);
            if (cur < minOff) aos.anchorXoffset = minOff;
            else if (cur > maxOff) aos.anchorXoffset = maxOff;
            try{ if (ip.parentStory && ip.parentStory.recompose) ip.parentStory.recompose(); }catch(__){}
        }catch(_){}
    }
    function clampIconToAnchorPage(obj, ip, pad){
        try{
            var tf = (ip.parentTextFrames && ip.parentTextFrames.length) ? ip.parentTextFrames[0] : null;
            var pg = tf ? tf.parentPage : (ip.parentPage ? ip.parentPage : null);
            if (!pg || !pg.isValid) return;
            var aos = obj.anchoredObjectSettings;
            if (!aos) return;
            var gbP = pg.bounds || pg.geometricBounds; 
            var left  = gbP[1] + pad;
            var right = gbP[3] - pad;
            var gbO = obj.geometricBounds; 
            var halfW = (gbO[3] - gbO[1]) / 2.0;
            var ipX = ip.horizontalOffset;
            var minOff = (left  + halfW) - ipX;
            var maxOff = (right - halfW) - ipX;
            var cur = (aos.anchorXoffset || 0);
            if (cur < minOff) aos.anchorXoffset = minOff;
            else if (cur > maxOff) aos.anchorXoffset = maxOff;
            // 강제 스냅: 여전히 반대 페이지라면 앵커 페이지 안쪽 경계로
            try{
                var objPg = obj.parentPage || (obj.parentTextFrames && obj.parentTextFrames.length ? obj.parentTextFrames[0].parentPage : null);
                if (objPg && pg && objPg != pg){
                    var gbO2 = obj.geometricBounds; 
                    var cx = (gbO2[1] + gbO2[3]) / 2.0;
                    var mid = (left + right) / 2.0;
                    if (cx > mid){
                        aos.anchorXoffset = (right - halfW) - ipX;
                    }else{
                        aos.anchorXoffset = (left + halfW) - ipX;
                    }
                }
            }catch(__){}
            try{ if (ip.parentStory && ip.parentStory.recompose) ip.parentStory.recompose(); }catch(__){}
        }catch(_){}
    }

    function wordStartIPFromHit(t){
        try{
            var w = t.words[0];
            if (w && w.isValid){
                return w.insertionPoints[0];
            }
        }catch(_){}
        try{ return t.insertionPoints[0]; }catch(__){}
        return null;
    }

    function insertInlineIconAtIP(srcItem, ip){
        var dup = srcItem.duplicate();
        dup.label = ICON_LABEL_PRIMARY;
        try { dup.anchoredObjectSettings.releaseAnchoredObject(); } catch(_){}
        var w = null;
        try{
            w = ip.words[0];
            if (!w || !w.isValid){ w = ip.parent.words[0]; }
        }catch(_){}
        dup.anchoredObjectSettings.insertAnchoredObject(ip, AnchorPosition.ANCHORED);
        dup.anchoredObjectSettings.anchoredPosition = AnchorPosition.ANCHORED;
        dup.anchoredObjectSettings.spineRelative = false;
        dup.anchoredObjectSettings.anchorPoint = AnchorPoint.BOTTOM_CENTER_ANCHOR;
        try{ dup.anchoredObjectSettings.horizontalReferencePoint = AnchoredRelativeTo.ANCHOR_LOCATION; }catch(_){}
        try{ dup.anchoredObjectSettings.verticalReferencePoint   = AnchoredRelativeTo.ANCHOR_LOCATION; }catch(_){}
        try{ dup.anchoredObjectSettings.lockPosition = false; }catch(_){}
        try{ dup.anchoredObjectSettings.anchorXoffset = 0; }catch(_){}
        try{ dup.anchoredObjectSettings.anchorYoffset = 0; }catch(_){}
        var xoff = XoffsetPT;
        try{
            if (w && w.isValid){
                var x0 = w.insertionPoints[0].horizontalOffset;
                var x1 = w.insertionPoints[-1].horizontalOffset;
                var wordCenter = (x0 + x1) / 2.0;
                var ipX = ip.horizontalOffset;
                xoff = (wordCenter - ipX) + XoffsetPT;
            }
        }catch(_){}
        try{ dup.anchoredObjectSettings.anchorXoffset = xoff; }catch(_){}
        try{ dup.anchoredObjectSettings.anchorYoffset = YoffsetPT; }catch(_){}
        clampIconToTextFrame(dup, ip, 1);
        clampIconToAnchorPage(dup, ip, 1);
        try{ if (ip.parentStory && ip.parentStory.recompose) ip.parentStory.recompose(); }catch(_){}
        try{ dup.bringToFront(); }catch(_){}
        return dup;
    }

    var src = findLabeledItem(ICON_LABEL_PRIMARY);
    if (!src){ alert("스크립트레이블 아이콘 '서술형아이콘'을 문서에 숨겨두세요."); return; }

    var srcWasLocked = src.locked; src.locked = false;
    try{ if (src.itemLayer){ src.itemLayer.locked = false; src.itemLayer.visible = true; } }catch(_){}
    var adjustedCount = adjustExistingIcons(NUDGE_DX, NUDGE_DY);
    // 위치 보정은 수행하되, 항상 이어서 재삽입/정렬/클램프 로직까지 계속 진행 (조기 종료하지 않음)

    var cs = getCharStyle(GROUP_CS, STYLE_CS);
    if (!cs){ alert("문자스타일 '"+GROUP_CS+"/"+STYLE_CS+"'을 찾을 수 없습니다."); return; }

    safeResetFindChange();
    app.findGrepPreferences.appliedCharacterStyle = cs;
    var hits = doc.findGrep();
    safeResetFindChange();

    var targets = [];
    var seen = {};
    for (var i=0; i<hits.length; i++){
        var t = hits[i];
        if (!t.isValid) continue;
        var para = t.paragraphs[0];
        var paraStart = para.insertionPoints[0];
        var ipHit = t.insertionPoints[0];
        var tmp = (function(){
            try{
                var tempRange = para.characters.itemByRange(paraStart, ipHit).texts[0];
                safeResetFindChange();
                app.findGrepPreferences.findWhat = "[.!]+";
                var marks = tempRange.findGrep();
                safeResetFindChange();
                if (marks && marks.length){
                    return marks[marks.length-1].insertionPoints[-1].index;
                }
                return paraStart.index;
            }catch(_){ try{ return paraStart.index; }catch(__){ return ipHit.index; } }
        })();
        var ipWord = wordStartIPFromHit(t);
        if (!ipWord || !ipWord.isValid) continue;
        var wordStartIndex = ipWord.index;
        var storySpec = (t.parentStory && t.parentStory.toSpecifier) ? t.parentStory.toSpecifier() : ("" + t.parentStory);
        var paraIndex = (typeof para.index === "number") ? para.index : 0;
        var key = storySpec + ":" + paraIndex + ":" + tmp;
        if (!seen[key] || (seen[key].wordStartIndex > wordStartIndex)){
            seen[key] = { storySpec: storySpec, paraIndex: paraIndex, startIndex: tmp, wordStartIndex: wordStartIndex, ip: ipWord };
        }
    }
    for (var kKey in seen){ if (seen.hasOwnProperty(kKey)) targets.push(seen[kKey]); }
    targets.sort(function(a,b){ return b.wordStartIndex - a.wordStartIndex; });
    for (var k=0; k<targets.length; k++){
        try{ insertInlineIconAtIP(src, targets[k].ip); }catch(e){}
    }
    safeResetFindChange();
    try{ src.locked = srcWasLocked; }catch(_){}
})();