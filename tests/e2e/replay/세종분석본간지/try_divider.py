"""contents 간지 찍기와 같은 요청을 임시 카탈로그의 스튜디오(테스트 클라이언트)에 — 학습 가이드 켬/끔 두 판"""
import os, sys, time, json
S = os.path.dirname(os.path.abspath(__file__))
WT, DESIGN = sys.argv[1], sys.argv[2]
os.environ["YONE_CATALOG_DIR"] = os.path.join(S, "cat_tmp")
os.environ["YONE_AUTH"] = "off"
os.environ["YONE_WARM"] = "0"
os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ["PATH"]
sys.path.insert(0, WT)
os.chdir(WT)
from studio_server import create_app                                    # noqa: E402
c = create_app().test_client()
for guide, lines in ((True, [{"book": "공통영어2 비상(홍) Unit 1", "lesson": "A Road Ahead"}]),
                     (False, [{"book": "공통영어2 비상(홍) 2과", "lesson": "My World, Your World"},
                              {"book": "EBS 리딩파워 유형편 (기본) Unit.1, 2, 3", "lesson": "Practice 03, 04"}])):
    body = {"series": "analysis", "design": DESIGN, "book": {"name": "시험 간지", "period": "", "title": "시험 간지"},
            "source": {"type": "data", "data": {"format": "yos-analysis-v1", "book": {"title": "시험"}, "analyses": [],
                                                "divider": {"school": "세종고", "volume": "1" if guide else "2", "lines": lines, "guide": guide}}},
            "print": True, "replace": True}
    r = c.post("/api/v1/renders", json=body)
    j = r.get_json()
    print(r.status_code, j)
    jid = j.get("job")
    for _ in range(120):
        st = c.get(f"/api/v1/renders/{jid}").get_json()
        if st.get("status") in ("done", "failed", "lost"):
            break
        time.sleep(1)
    print(json.dumps(st, ensure_ascii=False)[:900])
    for f in st.get("files") or []:
        name = f.get("name") if isinstance(f, dict) else f
        if str(name).endswith(".pdf"):
            data = c.get(f"/api/v1/renders/{jid}/files/{name}").data
            out = os.path.join(S, f"div_try_{'guide' if guide else 'plain'}.pdf")
            open(out, "wb").write(data)
            print(out, len(data))
