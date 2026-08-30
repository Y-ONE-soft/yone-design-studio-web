# webcore — 브라우저에서 도는 조판 엔진

작업대(`/book-studio`)가 **뷰어 앱 없이** 우리 화면 안에 지면을 앉히기 위한 묶음.

## 왜 필요했나

지금까지는 Vivliostyle **뷰어 앱**을 iframe 으로 물고 있었다. 그러면 그 앱의
툴바(목차·검색·글자 크기·인쇄…)가 화면 위쪽을 차지하는데 **우리가 그걸 못 바꾼다.**
조판 프로그램을 만들려면 화면이 우리 것이어야 한다.

`@vivliostyle/core` 의 `CoreViewer` 는 `viewportElement` 로 **우리 div** 를 받는다.
게다가

  · `documentObject`   파싱한 DOM 을 그대로 넘길 수 있다 (파일을 다시 안 읽는다)
  · `userStyleSheet`   CSS 를 문자열로 얹는다 → **색·여백을 서버 없이 그 자리에서**
  · `setOptions`       zoom · 펼침/낱쪽 · 화면맞춤 — 우리 툴바가 직접 건다

## 왜 묶어야 하나

`@vivliostyle/core` 는 번들러를 거치는 것을 전제로 나온다 — **전역도 export 도 없어서**
`<script>` 로 그냥 부르면 아무것도 안 잡힌다(여기서 한 번 헛짚었다). 그래서 vite 로
한 번 묶어 `window.VivlioCore` 로 올린다.

```bash
cd core/render_vivlio/webcore && ../node_modules/.bin/vite build --config vite.config.mjs
```

→ `dist/vivlio-core.js` (약 765KB). Flask 가 `/book-studio/core/…` 로 서빙한다.
`@vivliostyle/core` 판본을 올릴 때만 다시 묶으면 된다.

⚠ 뷰어 자원(`userAgentRootURL`)은 여전히 뷰어 패키지의 `resources/` 를 가리킨다
  (`/book-studio/viewer/resources/`).
