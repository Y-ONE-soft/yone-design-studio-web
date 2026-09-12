# 분석본 PDF 오른쪽 면 표본

Y.OS design(`~/dev/yos-design`)의 **실제 조판 엔진**으로 찍은 표본이다
(`proto/build.py` 의 prerender → Vivliostyle). 원고는 Y.OS 표본
`proto/data/kangdong_2509.txt` 이고, 동반의어 칸(품사·반의어·유의어)만
`source.txt` 에서 채웠다.

| 파일 | 판 | 오른쪽 면 |
|---|---|---|
| `yos_synonym.pdf` | 강동 2024(`_kangdong-2024`) | 동반의어 표 4칸 × 2벌(8칸), 흐름 상자는 빈 칸 넷 |
| `yos_synonym_baejae.pdf` | 배재(`baejae-H1-analysis`) | 같은 표인데 **칸 순서가 다르다** — 단어·뜻·품사·**반의어**·**동의어** |
| `yos_flownote.pdf` | 강동 25-9(`_kangdong-2509`) | `핵심기출문제 | FLOW NOTE` 두 단, NOTE 상자에 **글이 들어 있다** |

`yos_flownote.pdf` 의 NOTE 글은 상자에 직접 넣었다 — 오늘 Y.OS 는 NOTE 를 빈
상자로만 찍지만, 글이 든 분석본이 오면 그걸 읽어야 해서 같은 엔진·같은 CSS 로
찍어 둔 것이다.
