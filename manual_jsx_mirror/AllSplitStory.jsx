/* ===== InDesign ExtendScript (.jsx) =====
   문서 내 모든 스토리를 샘플 SplitStory.jsx로 분리
   - 마스터 페이지 프레임은 제외
   - 실제로 앞/뒤 프레임으로 연결된 스토리만 대상
   - 샘플 SplitStory.jsx가 없으면 TextFrame.splitStory()로 보조 시도
*/
(function () {
    if (app.documents.length === 0) { alert("열린 문서가 없습니다."); return; }
    var doc = app.activeDocument;

    // --- SplitStory.jsx 경로 탐색 ---
    function findSplitStoryFile(){
        var base = app.filePath.fsName;
        var candidates = [
            File(base + "/Scripts/Scripts Panel/Samples/JavaScript/SplitStory.jsx"),
            File(base + "/Scripts/Samples/JavaScript/SplitStory.jsx"),
            File(base + "/Scripts and Extensions/Scripts/Scripts Panel/Samples/JavaScript/SplitStory.jsx")
        ];
        for (var i=0;i<candidates.length;i++){
            try{ if (candidates[i].exists) return candidates[i]; }catch(_){}
        }
        return null;
    }

    // --- 마스터 페이지 여부 판단 ---
    function isOnMaster(tf){
        try{
            var p = tf.parentPage;
            if (!p) return false; // 스프레드에 직접 붙은 경우 등은 일반 페이지로 취급
            var parent = p.parent;
            return (parent && parent.constructor && parent.constructor.name === "MasterSpread");
        }catch(_){ return false; }
    }

    // --- 스토리별 대표 텍스트프레임 수집(연결된 프레임이 실제로 존재하는 경우만) ---
    var storyFirstFrameMap = {}; // key: story.id, val: first text frame
    (function collect(){
        var tfs = doc.textFrames.everyItem().getElements();
        for (var i=0;i<tfs.length;i++){
            var tf = tfs[i];
            if (!tf || !tf.isValid) continue;
            if (isOnMaster(tf)) continue; // 마스터 제외
            var st = null;
            try{ st = tf.parentStory; }catch(_){ st=null; }
            if (!st || !st.isValid) continue;

            // 연결 여부 체크(앞/뒤 프레임이 하나라도 있으면 스플릿 대상)
            var hasLink = !!(tf.previousTextFrame && tf.previousTextFrame.isValid) ||
                          !!(tf.nextTextFrame && tf.nextTextFrame.isValid);
            if (!hasLink) continue;

            // 해당 스토리의 "첫 번째 실 프레임"을 찾아 저장
            if (!storyFirstFrameMap[st.id]){
                // 그 스토리의 컨테이너들 중 일반 페이지 프레임을 우선으로 첫 프레임 선택
                var containers = st.textContainers;
                var first = null;
                for (var k=0;k<containers.length;k++){
                    var c = containers[k];
                    if (!c || !c.isValid) continue;
                    if (c.constructor && (c.constructor.name==="TextFrame" || c.constructor.name==="TextPath")){
                        if (isOnMaster(c)) continue;
                        first = c; break;
                    }
                }
                if (first) storyFirstFrameMap[st.id] = first;
            }
        }
    })();

    // 대상이 없으면 종료
    var storyIds = [];
    for (var sid in storyFirstFrameMap){ if (storyFirstFrameMap.hasOwnProperty(sid)) storyIds.push(sid); }
    if (storyIds.length === 0){
        alert("분리할 연결 스토리를 찾지 못했습니다.\n(이미 단일 프레임이거나 마스터 프레임만 있는 경우일 수 있습니다.)");
        return;
    }

    var splitFile = findSplitStoryFile();
    var _prevUIL = app.scriptPreferences.userInteractionLevel;
    var _prevRedraw = app.scriptPreferences.enableRedraw;

    try{
        app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
        app.scriptPreferences.enableRedraw = false;

        // 스토리별로 선택 후 샘플 SplitStory 실행
        for (var i=0;i<storyIds.length;i++){
            var firstFrame = storyFirstFrameMap[storyIds[i]];
            if (!firstFrame || !firstFrame.isValid) continue;

            // 선택
            try { app.selection = firstFrame; } catch(_){ try { app.select(firstFrame); } catch(__){} }

            // Split 실행
            if (splitFile){
                try{
                    app.doScript(
                        splitFile,
                        ScriptLanguage.JAVASCRIPT,
                        undefined,
                        UndoModes.ENTIRE_SCRIPT,
                        "SplitStory (Samples)"
                    );
                }catch(e_do){
                    // 보조 시도
                    try { app.doScript(File(splitFile), ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "SplitStory (Samples)"); } catch(__do2){}
                }
            } else {
                // 샘플 파일을 못 찾은 경우: 일부 환경에서는 API로 직접 분리 가능
                try{
                    if (typeof firstFrame.splitStory === "function"){
                        firstFrame.splitStory();
                    } else {
                        // 샘플이 없고 API도 없으면 1회만 경고 후 중단
                        alert("SplitStory.jsx를 찾을 수 없고, splitStory() 메서드도 사용할 수 없습니다.\nSamples 스크립트 설치를 확인하세요.");
                        break;
                    }
                }catch(e_api){}
            }
        }
    } finally {
        try { app.scriptPreferences.userInteractionLevel = _prevUIL; } catch(_){}
        try { app.scriptPreferences.enableRedraw = _prevRedraw; } catch(_){}
        try { doc.recompose(); app.redraw(); } catch(_){}
    }

    alert("모든 연결 스토리 분리를 완료했습니다. (" + storyIds.length + "개)");
})();