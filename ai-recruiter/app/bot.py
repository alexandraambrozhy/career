"""Telegram-бот: проводит кандидата через скрининг по вакансии.

Сценарий: /start vac_<id> → согласие на обработку ПД → имя → контакт →
скрининговые вопросы → резюме → оценка → уведомление рекрутера.
"""
import html
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove, User)

from .config import settings
from .db import Store
from .resume import extract_text
from .scoring import VERDICTS, score_candidate

log = logging.getLogger(__name__)
router = Router()
MAX_RESUME_BYTES = 10 * 1024 * 1024


class Screening(StatesGroup):
    consent = State()
    name = State()
    contact = State()
    question = State()
    resume = State()


def deep_link(bot_username: str, vacancy_id: int) -> str:
    return f"https://t.me/{bot_username}?start=vac_{vacancy_id}"


@router.message(CommandStart())
async def start(message: Message, command: CommandObject, state: FSMContext, store: Store):
    await state.clear()
    payload = command.args or ""
    if payload.startswith("vac_") and payload[4:].isdigit():
        vacancy = store.get_vacancy(int(payload[4:]))
        if vacancy and vacancy["active"]:
            return await _begin(message, state, vacancy)

    vacancies = store.list_vacancies(active_only=True)
    if not vacancies:
        return await message.answer("Сейчас открытых вакансий нет. Загляните позже!")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=v["title"], callback_data=f"vac:{v['id']}")] for v in vacancies
    ])
    await message.answer("Привет! Выберите вакансию, на которую хотите откликнуться:", reply_markup=kb)


@router.callback_query(F.data.startswith("vac:"))
async def pick_vacancy(cb: CallbackQuery, state: FSMContext, store: Store):
    vacancy = store.get_vacancy(int(cb.data.split(":")[1]))
    await cb.answer()
    if not vacancy or not vacancy["active"]:
        return await cb.message.answer("Эта вакансия уже закрыта.")
    await _begin(cb.message, state, vacancy)


async def _begin(message: Message, state: FSMContext, vacancy: dict):
    await state.set_state(Screening.consent)
    await state.update_data(vacancy_id=vacancy["id"], answers=[], q_index=0)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Согласен(на)", callback_data="consent:yes"),
        InlineKeyboardButton(text="Отказаться", callback_data="consent:no"),
    ]])
    await message.answer(
        f"<b>{html.escape(vacancy['title'])}</b>\n\n{html.escape(vacancy['description'])}\n\n"
        "Я задам несколько вопросов и попрошу резюме — это займёт около 5 минут.\n\n"
        "Для продолжения нужно согласие на обработку персональных данных "
        "(имя, контакты, резюме) в целях подбора персонала.",
        reply_markup=kb,
    )


@router.callback_query(Screening.consent, F.data.startswith("consent:"))
async def consent(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    if cb.data.endswith("no"):
        await state.clear()
        return await cb.message.answer("Хорошо, данные не сохраняются. Если передумаете — нажмите /start.")
    await state.set_state(Screening.name)
    await cb.message.answer("Как вас зовут? Напишите имя и фамилию.")


@router.message(Screening.name, F.text)
async def got_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip()[:200])
    await state.set_state(Screening.contact)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отправить номер телефона", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True,
    )
    await message.answer("Оставьте телефон или email для связи:", reply_markup=kb)


@router.message(Screening.contact, F.contact | F.text)
async def got_contact(message: Message, state: FSMContext, store: Store):
    contact = message.contact.phone_number if message.contact else message.text.strip()[:200]
    await state.update_data(contact=contact)
    await message.answer("Спасибо!", reply_markup=ReplyKeyboardRemove())
    await _ask_next(message, state, store)


async def _ask_next(message: Message, state: FSMContext, store: Store):
    data = await state.get_data()
    questions = store.get_vacancy(data["vacancy_id"])["questions"]
    i = data["q_index"]
    if i < len(questions):
        await state.set_state(Screening.question)
        return await message.answer(f"Вопрос {i + 1} из {len(questions)}:\n{questions[i]}")
    await state.set_state(Screening.resume)
    await message.answer(
        "Последний шаг — пришлите резюме файлом (PDF, DOCX или TXT) "
        "или вставьте текст сообщением. Если резюме нет — отправьте /skip."
    )


@router.message(Screening.question, F.text)
async def got_answer(message: Message, state: FSMContext, store: Store):
    data = await state.get_data()
    questions = store.get_vacancy(data["vacancy_id"])["questions"]
    answers = data["answers"] + [{"question": questions[data["q_index"]], "answer": message.text.strip()}]
    await state.update_data(answers=answers, q_index=data["q_index"] + 1)
    await _ask_next(message, state, store)


async def read_resume(message: Message) -> str:
    """Текст резюме из присланного файла. ValueError — с понятным кандидату текстом."""
    doc = message.document
    if doc.file_size and doc.file_size > MAX_RESUME_BYTES:
        raise ValueError("Файл слишком большой (максимум 10 МБ)")
    buf = await message.bot.download(doc)
    try:
        return extract_text(doc.file_name or "resume", buf.read())
    except ValueError:
        raise
    except Exception:
        log.exception("resume parse failed")
        raise ValueError("Не удалось прочитать файл")


@router.message(Screening.resume, F.document)
async def got_resume_file(message: Message, state: FSMContext, store: Store):
    try:
        text = await read_resume(message)
    except ValueError as e:
        return await message.answer(f"{e}. Попробуйте другой файл или вставьте текст.")
    await _finish(message, state, store, text, message.document.file_name)


@router.message(Screening.resume, F.text)
async def got_resume_text(message: Message, state: FSMContext, store: Store):
    text = "" if message.text.strip() == "/skip" else message.text
    await _finish(message, state, store, text, None)


async def _finish(message: Message, state: FSMContext, store: Store, resume_text: str, filename: str | None):
    data = await state.get_data()
    await state.clear()
    await message.answer("Спасибо! Анкета отправлена, рекрутер свяжется с вами, если профиль подойдёт.")
    await submit_application(message.bot, store, data, message.from_user, resume_text, filename)


async def submit_application(bot: Bot, store: Store, data: dict, user: User, resume_text: str,
                             filename: str | None, notify_chat_ids: tuple[int, ...] = ()) -> int:
    """Оценивает анкету, сохраняет кандидата и уведомляет рекрутеров, если он выше порога."""
    vacancy = store.get_vacancy(data["vacancy_id"])
    try:
        result = await score_candidate(vacancy, data["answers"], resume_text)
        fields = result.as_fields()
    except Exception:
        log.exception("scoring failed")
        fields = {"summary": "Ошибка автоматической оценки — проверьте кандидата вручную."}

    candidate_id = store.create_candidate(
        vacancy["id"],
        tg_user_id=user.id,
        tg_username=user.username,
        name=data["name"],
        contact=data["contact"],
        answers=data["answers"],
        resume_text=resume_text,
        resume_filename=filename,
        **fields,
    )
    score = fields.get("score")
    if score is not None and score >= vacancy["threshold"]:
        chat_ids = dict.fromkeys([*settings.recruiter_chat_ids, *notify_chat_ids])
        await _notify_recruiters(bot, vacancy, store.get_candidate(candidate_id), chat_ids)
    return candidate_id


async def _notify_recruiters(bot: Bot, vacancy: dict, cand: dict, chat_ids):
    username = f" (@{cand['tg_username']})" if cand["tg_username"] else ""
    text = (
        f"🔥 Новый подходящий кандидат — <b>{html.escape(vacancy['title'])}</b>\n\n"
        f"<b>{html.escape(cand['name'])}</b>{html.escape(username)}\n"
        f"Контакт: {html.escape(cand['contact'])}\n"
        f"Оценка: <b>{cand['score']}/100</b> — {VERDICTS.get(cand['verdict'], '')}\n\n"
        f"{html.escape(cand['summary'] or '')}\n\n"
        f"Карточка: {settings.public_url}/candidates/{cand['id']}"
    )
    for chat_id in chat_ids:
        try:
            await bot.send_message(chat_id, text)
        except Exception:
            log.exception("failed to notify recruiter %s", chat_id)


def build_dispatcher(store: Store) -> Dispatcher:
    from .business import router as business_router

    dp = Dispatcher(store=store)
    dp.include_routers(router, business_router)
    return dp
