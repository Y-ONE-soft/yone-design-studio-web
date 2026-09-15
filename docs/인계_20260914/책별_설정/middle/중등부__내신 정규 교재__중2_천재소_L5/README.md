# 중2 천재(소영순) Lesson 05 — 「같이새김」 1권 · 「홀로새김」 2권

조판 코드와 문서는 이 폴더에 없다. 한 단계 위 `../README.md` 와 `../automation/` 이
모든 교재를 함께 조판한다.

```bash
cd "../automation"
python3 build.py  cheonjae 1     # 또는 cheonjae 2
python3 verify.py cheonjae 1
python3 press.py  cheonjae 1
```

`_backup/` 은 **회귀 기준선**이다 — 파이프라인을 손댔으면 두 권을 다시 빌드해
`_backup/fingerprint.json` 의 면 수·본문 해시·면별 픽셀 해시와 전부 같은지 확인한다.
이 폴더에는 그 밖에 `원고/` 와 산출 PDF 만 둔다.
