#target "indesign"
app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
function main(){
  // activate the doc whose filename contains the target (passed via ACTIVATE_TARGET file marker)
  var want=""; try{ var mf=new File("/private/tmp/claude-501/-Users-nhj-dev---/f6c6c025-b945-469f-9f16-f4f7e4939275/scratchpad/activate_target.txt"); if(mf.open("r")){ want=mf.read(); mf.close(); want=want.replace(/[\r\n]/g,""); } }catch(e){}
  for(var i=0;i<app.documents.length;i++){ var d=app.documents[i];
    var fp=""; try{fp=decodeURI(String(d.fullName));}catch(e){fp=String(d.fullName);}
    // normalize: strip to just check school digit-name via file basename bytes
    if(fp.indexOf(want)>=0){ app.activeDocument=d; return "activated "+d.name+" pages="+d.pages.length; }
  }
  return "not found want="+want+" openDocs="+app.documents.length;
}
try{ main(); }catch(e){ "ERR "+e.toString()+" @"+e.line; }
