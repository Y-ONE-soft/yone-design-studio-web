# 중2 동아(윤정미) Lesson 05 — 「같이새김」 1권

조판 코드와 문서는 이 폴더에 없다. 한 단계 위 `../README.md` 와 `../automation/` 이
모든 교재를 함께 조판한다.

```bash
cd "../automation"
python3 build.py  donga 1
python3 verify.py donga 1
python3 press.py  donga 1
```

이 폴더에는 `원고/` 와 산출 PDF 만 둔다.
