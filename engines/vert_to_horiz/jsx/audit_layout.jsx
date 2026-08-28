// [ENGINE TEMPLATE] 산출물 지면 검수 — 오버셋 / 빈 칸 / 실전 순서
//
// 텍스트 대조(v2h_content_diff)는 "내용이 있는가"만 본다. 그것만으로
// 검수했다고 하면 **지면이 깨져 있어도 통과한다**(2026-08-25: 유실 0 통과
// 산출물에 오버셋 2건·빈 프레임 21건이 있었고, 보고에서 빠졌다).
//
// 여기서는 지면 상태를 센다:
//   [1] 오버셋 프레임 — 프레임 밖으로 밀려 인쇄되지 않는 텍스트
//   [2] 빈 본문 프레임 — 채워지지 않은 칸
//   [3] 실전 지문 순서 — 마커 등장 순서가 강 순서와 맞는가
//
// ⚠ 세로중간본에도 같은 검수를 돌려 **비교**할 것. 빈 칸·오버셋은 세로에서
//   넘어오는 경우가 많다(실측: 세로 26/7건 → 가로 21/2건). 가로 수치만 보면
//   조판 결함으로 오진한다.
#target indesign
(function () {
    var settingsPath = "__OUT__";
    var SRC = "__SRC__", OUT = "__OUT__";
    var buf = [];
    function W(s) {
        buf.push(String(s));
        var f = new File(OUT); f.encoding="UTF-8"; f.lineFeed="Unix";
        f.open("w"); f.write(buf.join("\n")+"\n"); f.close();
    }
    var doc=null, ours=false;
    var fo=new File(SRC);
    for (var d=0; d<app.documents.length; d++){
        try{ if(String(app.documents[d].fullName)===String(fo)) doc=app.documents[d]; }catch(e){}
    }
    if(!doc){ doc=app.open(fo,false); ours=true; }
    W("검수 대상: " + decodeURI(fo.name) + " / 총 " + doc.pages.length + "p");

    // 1) 오버셋 프레임 전수
    W("\n[1] 오버셋 프레임");
    var ovN=0;
    for (var p=0; p<doc.pages.length; p++){
        var pg=doc.pages[p], sp=pg.parent;
        for (var i=0;i<sp.textFrames.length;i++){
            var tf=sp.textFrames[i];
            if(!tf.parentPage || tf.parentPage.id!==pg.id) continue;
            var ov=false; try{ ov=tf.overflows; }catch(e1){ continue; }
            if(!ov) continue;
            ovN++;
            var shown=0, all=0;
            try{ shown=tf.lines.length; all=tf.parentStory.lines.length; }catch(e2){}
            var c=""; try{ c=String(tf.contents).replace(/[\r\n\t]+/g," "); }catch(e3){}
            W("  p"+pg.name+" 보이는줄 "+shown+"/"+all+" | "+c.replace(/^\s+/,"").substring(0,50));
        }
    }
    W("  → 오버셋 프레임 " + ovN + "개");

    // 2) 빈 프레임 (내용 없는 본문 프레임)
    W("\n[2] 빈 본문 프레임");
    var emptyN=0;
    for (var p2=0; p2<doc.pages.length; p2++){
        var pg2=doc.pages[p2], sp2=pg2.parent;
        for (var j=0;j<sp2.textFrames.length;j++){
            var tf2=sp2.textFrames[j];
            if(!tf2.parentPage || tf2.parentPage.id!==pg2.id) continue;
            var gb2=tf2.geometricBounds;
            if (gb2[0] < 0) continue;                 // 사이드 라벨 제외
            if ((gb2[2]-gb2[0]) < 60) continue;       // 작은 장식 프레임 제외
            var c2=""; try{ c2=String(tf2.contents); }catch(e4){}
            if (c2.replace(/[\s\r\n￼]/g,"").length===0){
                emptyN++;
                if (emptyN<=20) W("  p"+pg2.name+" y"+Math.round(gb2[0])+"~"+Math.round(gb2[2]));
            }
        }
    }
    W("  → 빈 본문 프레임 " + emptyN + "개");

    // 3) 실전(STEP3) 페이지 순서 — {코드}/6자리 마커 등장 순서
    W("\n[3] 실전 지문 순서 (마커 등장 순)");
    var seen={}, order=[];
    for (var p3=0; p3<doc.pages.length; p3++){
        var pg3=doc.pages[p3];
        for (var k=0;k<pg3.textFrames.length;k++){
            var c3=""; try{ c3=String(pg3.textFrames[k].contents); }catch(e5){ continue; }
            var m=c3.match(/\d{6}/g);
            if(!m) continue;
            for (var q=0;q<m.length;q++){
                if(!seen[m[q]]){ seen[m[q]]=1; order.push(m[q]+"@p"+pg3.name); }
            }
        }
    }
    W("  " + order.join("  "));

    W("\n===== 검수 완료 =====");
    if(ours) doc.close(SaveOptions.NO);
})();
