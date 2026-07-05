#target "indesign"
#include "answerdata_active.jsx"  // var ANSWERS [{n,t,ans:[[t,f]],expl:[[[t,f]]]}]
app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
function main(){
  var doc=app.activeDocument; if(!doc) return "NO DOC";
  var out="";
  function getPS(n){var a=doc.allParagraphStyles;for(var i=0;i<a.length;i++)if(a[i].name==n)return a[i];return null;}
  function getCS(n){var a=doc.allCharacterStyles;for(var i=0;i<a.length;i++)if(a[i].name==n)return a[i];return null;}
  var NONE=getCS("[없음]");
  var PS_ENTRY=getPS("실전문제 해설")||getPS("해설"), PS_SOL=getPS("해설"), PS_CONT=getPS("해설 사본")||getPS("해설"), PS_TYPE=getPS("기출_유형")||PS_SOL;
  var CS_NUM=getCS("해설_번호"), CS_ANS=getCS("해설_정답바"), CS_SOL=getCS("해설"), CS_HDR=getCS("헤더_챕터");
  var CS_U=getCS("문제_밑줄"), CS_B=getCS("기출_볼드"), CS_RED=getCS("기출_빨강");
  // 답 번호는 수동 "N)"으로 부으므로: 스타일의 자동번호(01,02..) 제거 + 번호를 1%로 찌그러뜨리는
  // nested GREP("^\d+?\)"->문자스타일5,hScale=1) 제거(사용자 지적: 번호 1% squish 대신 삭제).
  try{ if(PS_ENTRY && PS_ENTRY.name=="실전문제 해설"){
    PS_ENTRY.bulletsAndNumberingListType=ListType.NO_LIST;
    var _ng=PS_ENTRY.nestedGrepStyles;
    for(var _gi=_ng.length-1;_gi>=0;_gi--){ if(String(_ng[_gi].grepExpression)=="^\\d+?\\)") _ng[_gi].remove(); }
  } }catch(e){ out+="numFix:"+e+"; "; }

  var gStart=-1,hEnd=-1;
  for(var pi=0;pi<doc.pages.length;pi++){ var mn=doc.pages[pi].appliedMaster?doc.pages[pi].appliedMaster.namePrefix:"";
    if((mn=="G"||mn=="H")){ if(gStart<0)gStart=pi; hEnd=pi; } }
  if(gStart<0) return "NO 정답 PAGES";
  var gMaster=doc.pages[gStart].appliedMaster;
  var tmplL=[29,14,276,191], tmplR=[29,17,276,194], cols=2, gutter=5;
  var first=doc.pages[gStart];
  for(var f=0;f<first.textFrames.length;f++){ var tf=first.textFrames[f]; if(tf.geometricBounds[0]>15){ var gb=tf.geometricBounds; if(first.side==1818653800) tmplL=gb.concat(); else tmplR=gb.concat(); try{cols=tf.textFramePreferences.textColumnCount; gutter=tf.textFramePreferences.textColumnGutter;}catch(e){} break; } }
  for(var f=first.textFrames.length-1;f>=0;f--){ if(first.textFrames[f].geometricBounds[0]>15) first.textFrames[f].remove(); }
  for(var pi=hEnd; pi>gStart; pi--){ try{ doc.pages[pi].remove(); }catch(e){} }
  function geoFor(pg){ return (pg.side==1818653800)?tmplL:tmplR; }
  var fr=first.textFrames.add(); fr.geometricBounds=geoFor(first);
  try{ fr.textFramePreferences.textColumnCount=cols; fr.textFramePreferences.textColumnGutter=gutter; }catch(e){}
  var story=fr.parentStory;

  function ins(runs,defCS){ for(var r=0;r<runs.length;r++){ var t=runs[r][0]; if(t==="")continue; var ff=runs[r][1]||"";
      var a=story.length; story.insertionPoints[-1].contents=t; var b=story.length; if(b<=a)continue;
      var rng=story.characters.itemByRange(a,b-1); try{rng.appliedCharacterStyle=NONE;rng.clearOverrides(OverrideType.CHARACTER_ONLY);}catch(e){}
      var cs=defCS;
      if(ff.indexOf('u')>=0)cs=CS_U; else if(ff.indexOf('r')>=0)cs=CS_RED; else if(ff.indexOf('b')>=0)cs=CS_B;
      if(cs){try{rng.appliedCharacterStyle=cs;}catch(e){}} } }
  // insert paragraph break BEFORE content; set the paragraph style AFTER content.
  // (InDesign: right after inserting "\r", the empty trailing paragraph is not yet
  //  paragraphs[-1], so styling before content lands it on the PREVIOUS paragraph —
  //  that off-by-one is why 세종1 유형헤더/정답줄/해설 스타일이 한 칸씩 밀렸다.)
  function brk(){ if(story.length>0) story.insertionPoints[-1].contents="\r"; }
  function setPS(ps){ try{ story.paragraphs[-1].appliedParagraphStyle=ps; }catch(e){} }

  var curType=null, poured=0;
  for(var k=0;k<ANSWERS.length;k++){ var A=ANSWERS[k];
    if(A.t!==curType){ curType=A.t; if(curType&&curType!==""){ brk(); ins([[curType,""]], CS_HDR); setPS(PS_TYPE); } }
    // answer line: "N) 정답"
    brk(); ins([[A.n+") ",""]], CS_NUM); ins(A.ans, CS_ANS); setPS(PS_ENTRY);
    // explanation: first=해설, rest=해설 사본
    for(var e=0;e<A.expl.length;e++){ brk(); ins(A.expl[e], CS_SOL); setPS(e==0?PS_SOL:PS_CONT); }
    poured++;
  }
  out+="poured "+poured+", overflow="+story.overflows+"; ";
  var guard=0;
  while(story.overflows && guard<50){ var conts=story.textContainers; var lastF=conts[conts.length-1]; var lastPg=lastF.parentPage;
    var np=doc.pages.add(LocationOptions.AFTER,lastPg); try{np.appliedMaster=gMaster;}catch(e){}
    var nf=np.textFrames.add(); nf.geometricBounds=geoFor(np); try{nf.textFramePreferences.textColumnCount=cols; nf.textFramePreferences.textColumnGutter=gutter;}catch(e){}
    lastF.nextTextFrame=nf; guard++; }
  out+="autoflow+"+guard+" totalPages="+doc.pages.length;
  doc.recompose(); doc.save();
  app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
  return out;
}
try{ main(); }catch(e){ "ERR "+e.toString()+" @"+e.line; }
