"""Веб-панель рекрутера: вакансии, рейтинг кандидатов, карточки, статусы."""
import csv
import io
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from .config import settings
from .db import STATUSES, Store
from .scoring import VERDICTS

security = HTTPBasic()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def require_admin(creds: HTTPBasicCredentials = Depends(security)) -> None:
    ok_user = secrets.compare_digest(creds.username.encode(), settings.admin_user.encode())
    ok_pass = secrets.compare_digest(creds.password.encode(), settings.admin_password.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def create_app(store: Store, bot_username: str | None = None) -> FastAPI:
    app = FastAPI(title="AI-рекрутер", dependencies=[Depends(require_admin)])
    ctx = {"statuses": STATUSES, "verdicts": VERDICTS, "demo_mode": settings.demo_mode,
           "bot_username": bot_username}

    def render(request: Request, name: str, **kw) -> HTMLResponse:
        return templates.TemplateResponse(request, name, {**ctx, **kw})

    def vacancy_or_404(vacancy_id: int) -> dict:
        vacancy = store.get_vacancy(vacancy_id)
        if not vacancy:
            raise HTTPException(404, "Вакансия не найдена")
        return vacancy

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return render(request, "index.html", vacancies=store.list_vacancies())

    @app.post("/vacancies")
    def create_vacancy(title: str = Form(...), description: str = Form(""),
                       requirements: str = Form(""), questions: str = Form(""),
                       threshold: int = Form(70)):
        vacancy_id = store.create_vacancy(title.strip(), description.strip(), requirements.strip(),
                                          _lines(questions), max(0, min(100, threshold)))
        return RedirectResponse(f"/vacancies/{vacancy_id}", status_code=303)

    @app.get("/vacancies/{vacancy_id}", response_class=HTMLResponse)
    def vacancy_page(request: Request, vacancy_id: int):
        vacancy = vacancy_or_404(vacancy_id)
        return render(request, "vacancy.html", vacancy=vacancy,
                      candidates=store.list_candidates(vacancy_id))

    @app.post("/vacancies/{vacancy_id}")
    def update_vacancy(vacancy_id: int, title: str = Form(...), description: str = Form(""),
                       requirements: str = Form(""), questions: str = Form(""),
                       threshold: int = Form(70)):
        vacancy_or_404(vacancy_id)
        store.update_vacancy(vacancy_id, title=title.strip(), description=description.strip(),
                             requirements=requirements.strip(), questions=_lines(questions),
                             threshold=max(0, min(100, threshold)))
        return RedirectResponse(f"/vacancies/{vacancy_id}", status_code=303)

    @app.post("/vacancies/{vacancy_id}/toggle")
    def toggle_vacancy(vacancy_id: int):
        vacancy = vacancy_or_404(vacancy_id)
        store.update_vacancy(vacancy_id, active=0 if vacancy["active"] else 1)
        return RedirectResponse(f"/vacancies/{vacancy_id}", status_code=303)

    @app.get("/vacancies/{vacancy_id}/export.csv")
    def export_csv(vacancy_id: int):
        vacancy = vacancy_or_404(vacancy_id)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "Имя", "Контакт", "Telegram", "Оценка", "Вердикт", "Статус",
                         "Сводка", "Дата"])
        for c in store.list_candidates(vacancy_id):
            writer.writerow([c["id"], c["name"], c["contact"],
                             f"@{c['tg_username']}" if c["tg_username"] else "",
                             c["score"], VERDICTS.get(c["verdict"], ""), STATUSES[c["status"]],
                             c["summary"], c["created_at"]])
        filename = f"candidates_{vacancy['id']}.csv"
        return StreamingResponse(
            iter(["﻿" + buf.getvalue()]),  # BOM, чтобы Excel открыл кириллицу
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/candidates/{candidate_id}", response_class=HTMLResponse)
    def candidate_page(request: Request, candidate_id: int):
        cand = store.get_candidate(candidate_id)
        if not cand:
            raise HTTPException(404, "Кандидат не найден")
        return render(request, "candidate.html", cand=cand,
                      vacancy=store.get_vacancy(cand["vacancy_id"]))

    @app.post("/candidates/{candidate_id}/status")
    def candidate_status(candidate_id: int, status: str = Form(...)):
        cand = store.get_candidate(candidate_id)
        if not cand:
            raise HTTPException(404, "Кандидат не найден")
        if status not in STATUSES:
            raise HTTPException(400, "Неизвестный статус")
        store.set_status(candidate_id, status)
        return RedirectResponse(f"/candidates/{candidate_id}", status_code=303)

    return app
