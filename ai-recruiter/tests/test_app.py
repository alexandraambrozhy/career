import asyncio
import base64

import pytest
from fastapi.testclient import TestClient

from app.db import Store
from app.resume import extract_text
from app.scoring import build_prompt, demo_score, score_candidate
from app.web import create_app

VACANCY = {
    "id": 1, "title": "Python-разработчик", "description": "Бэкенд сервиса",
    "requirements": "Python, FastAPI, PostgreSQL, Docker", "questions": [], "threshold": 70,
}
AUTH = {"Authorization": "Basic " + base64.b64encode(b"admin:admin").decode()}


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / "test.db"))


def test_demo_score_matches_keywords():
    full = demo_score(VACANCY, [], "5 лет пишу на Python, FastAPI, PostgreSQL и Docker")
    assert full.score == 100 and full.verdict == "fit"
    partial = demo_score(VACANCY, [{"question": "Стек?", "answer": "Python"}], "")
    assert partial.score == 25 and partial.verdict == "no_fit"
    assert any("docker" in r for r in partial.risks)


def test_score_candidate_uses_demo_without_key():
    result = asyncio.run(score_candidate(VACANCY, [], "Python FastAPI"))
    assert result.score == 50


def test_prompt_wraps_candidate_data_in_tags():
    prompt = build_prompt(VACANCY, [{"question": "Q", "answer": "A"}], "резюме")
    assert "<resume>\nрезюме\n</resume>" in prompt
    assert "В: Q\nО: A" in prompt


def test_store_roundtrip(store):
    vid = store.create_vacancy("Аналитик", "", "SQL", ["Опыт?"], 60)
    cid = store.create_candidate(vid, name="Анна", contact="+7900", answers=[{"question": "Опыт?", "answer": "3 года"}],
                                 score=80, verdict="fit", strengths=["SQL"])
    low = store.create_candidate(vid, name="Борис", contact="b@x.ru", score=40)
    assert [c["id"] for c in store.list_candidates(vid)] == [cid, low]
    assert store.get_candidate(cid)["answers"][0]["answer"] == "3 года"
    v = store.list_vacancies()[0]
    assert v["candidates_total"] == 2 and v["candidates_fit"] == 1
    store.set_status(cid, "shortlist")
    assert store.get_candidate(cid)["status"] == "shortlist"
    with pytest.raises(ValueError):
        store.set_status(cid, "hacked")


def test_extract_text_txt_and_unsupported():
    assert extract_text("cv.txt", "Иван Петров".encode()) == "Иван Петров"
    with pytest.raises(ValueError):
        extract_text("cv.exe", b"")


def test_web_panel(store):
    client = TestClient(create_app(store, "my_hr_bot"))
    assert client.get("/").status_code == 401

    r = client.post("/vacancies", headers=AUTH, follow_redirects=False, data={
        "title": "Менеджер", "requirements": "CRM", "questions": "Опыт?\n\nЗарплата?", "threshold": "75"})
    assert r.status_code == 303
    vid = int(r.headers["location"].rsplit("/", 1)[1])
    assert store.get_vacancy(vid)["questions"] == ["Опыт?", "Зарплата?"]

    cid = store.create_candidate(vid, name="Ольга", contact="+7999", score=90, verdict="fit",
                                 summary="<script>x</script>")
    page = client.get(f"/vacancies/{vid}", headers=AUTH).text
    assert "https://t.me/my_hr_bot?start=vac_" in page and "Ольга" in page
    assert "<script>x</script>" not in page

    r = client.post(f"/candidates/{cid}/status", headers=AUTH, data={"status": "interview"},
                    follow_redirects=False)
    assert r.status_code == 303 and store.get_candidate(cid)["status"] == "interview"
    assert client.get(f"/candidates/{cid}", headers=AUTH).status_code == 200

    csv_text = client.get(f"/vacancies/{vid}/export.csv", headers=AUTH).text
    assert "Ольга" in csv_text and "Интервью" in csv_text
