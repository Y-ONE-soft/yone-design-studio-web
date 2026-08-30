// 브라우저에서 쓰는 Vivliostyle 조판 엔진.
//
// `@vivliostyle/core` 는 번들러를 거치는 것을 전제로 나온다(전역도 export 도 없다).
// 그래서 여기서 한 번 묶어 `window.VivlioCore` 로 올린다. 이걸 쓰면 **뷰어 앱 없이**
// 우리 화면 안의 div 에 지면을 앉힐 수 있다 — 조판 프로그램의 캔버스가 된다.
import * as Core from "@vivliostyle/core";
window.VivlioCore = Core;
