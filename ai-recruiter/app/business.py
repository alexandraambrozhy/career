"""Режим Telegram Business: кандидат пишет рекрутеру в личный аккаунт,
бот ведёт скрининг в этом же чате от имени рекрутера.

Если рекрутер сам напишет в чат, бот замолкает в нём навсегда — дальше общается человек.
"""
import html
import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BusinessConnection, Message

from .bot import read_resume, submit_application
from .db import Store

log = logging.getLogger(__name__)
router = Router()

YES = {"да", "ага", "ок", "ok", "окей", "+", "согласен", "согласна", "конечно", "yes", "давайте"}
NO_RESUME = {"нет", "нету", "нет резюме", "без резюме", "-", "/skip"}


class BizScreening(StatesGroup):
    vacancy = State()
    consent = State()
    name = State()
    contact = State()
    question = State()
    resume = State()
    done = State()


_connections: dict[str, BusinessConnection] = {}


async def _connection(bot: Bot, connection_id: str) -> BusinessConnection:
    if connection_id not in _connections:
        _connections[connection_id] = await bot.get_business_connection(connection_id)
    return _connections[connection_id]


@router.business_connection()
async def on_connection(connection: BusinessConnection, bot: Bot):
    _connections[connection.id] = connection
    if not connection.is_enabled:
        return
    can_reply = connection.rights.can_reply if connection.rights else connection.can_reply
    text = ("Бот подключён к вашему аккаунту. Кандидаты, которые напишут вам первыми, "
            "получат ответ от вашего имени и пройдут скрининг. Если напишете в чат сами — "
            "бот в нём замолкнет.")
    if not can_reply:
        text = ("Бот подключён, но без права отвечать. Включите «Отвечать на сообщения» в "
                "Настройки → Telegram для бизнеса → Чат-боты.")
    await bot.send_message(connection.user_chat_id, text)


async def _from_owner(message: Message, bot: Bot) -> bool:
    connection = await _connection(bot, message.business_connection_id)
    return message.from_user is not None and message.from_user.id == connection.user.id


async def _paused(message: Message, store: Store) -> bool:
    return store.is_paused(message.business_connection_id, message.chat.id)


@router.business_message(_from_owner)
async def owner_wrote(message: Message, store: Store):
    # рекрутер вмешался в диалог — дальше общается сам
    store.pause_chat(message.business_connection_id, message.chat.id)


@router.business_message(_paused)
@router.business_message(BizScreening.done)
async def ignore(message: Message):
    pass


@router.business_message(StateFilter(None))
async def first_message(message: Message, state: FSMContext, store: Store):
    if message.chat.type != "private":
        return
    if store.has_applied(message.from_user.id):
        return await state.set_state(BizScreening.done)

    vacancies = store.list_vacancies(active_only=True)
    if not vacancies:
        return await state.set_state(BizScreening.done)  # нечего предлагать — отвечает человек

    text = (message.text or message.caption or "").lower()
    matched = [v for v in vacancies if v["title"].lower() in text]
    if len(vacancies) == 1 or len(matched) == 1:
        return await _offer(message, state, (matched or vacancies)[0])

    await state.set_state(BizScreening.vacancy)
    await state.update_data(vacancy_ids=[v["id"] for v in vacancies])
    options = "\n".join(f"{i}. {v['title']}" for i, v in enumerate(vacancies, 1))
    await message.answer(f"Здравствуйте! Спасибо, что написали 🙂\n"
                         f"Подскажите, по какой вакансии? Пришлите номер:\n\n{options}")


@router.business_message(BizScreening.vacancy, F.text)
async def picked_vacancy(message: Message, state: FSMContext, store: Store):
    ids = (await state.get_data())["vacancy_ids"]
    digits = re.sub(r"\D", "", message.text)
    if not digits or not 1 <= int(digits) <= len(ids):
        return await message.answer(f"Пришлите, пожалуйста, номер от 1 до {len(ids)}.")
    await _offer(message, state, store.get_vacancy(ids[int(digits) - 1]), greet=False)


async def _offer(message: Message, state: FSMContext, vacancy: dict, greet: bool = True):
    await state.set_state(BizScreening.consent)
    await state.update_data(vacancy_id=vacancy["id"], answers=[], q_index=0)
    hello = "Здравствуйте! Спасибо, что написали 🙂\n\n" if greet else ""
    await message.answer(
        f"{hello}<b>{html.escape(vacancy['title'])}</b>\n{html.escape(vacancy['description'])}\n\n"
        "Задам несколько коротких вопросов — это займёт около 5 минут. "
        "Вы согласны на обработку персональных данных (имя, контакты, резюме) для подбора? "
        "Ответьте «да», чтобы продолжить."
    )


@router.business_message(BizScreening.consent, F.text)
async def got_consent(message: Message, state: FSMContext):
    answer = message.text.strip().lower().rstrip("!.)")
    if answer in YES or answer.startswith("да"):
        await state.set_state(BizScreening.name)
        return await message.answer("Отлично! Как к вам обращаться? Напишите имя и фамилию.")
    await state.set_state(BizScreening.done)
    await message.answer("Хорошо, понимаю. Если появятся вопросы по вакансии — напишите.")


@router.business_message(BizScreening.name, F.text)
async def got_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip()[:200])
    await state.set_state(BizScreening.contact)
    await message.answer("Оставьте, пожалуйста, телефон или email для связи.")


@router.business_message(BizScreening.contact, F.contact | F.text)
async def got_contact(message: Message, state: FSMContext, store: Store):
    contact = message.contact.phone_number if message.contact else message.text.strip()[:200]
    await state.update_data(contact=contact)
    await _ask_next(message, state, store)


async def _ask_next(message: Message, state: FSMContext, store: Store):
    data = await state.get_data()
    questions = store.get_vacancy(data["vacancy_id"])["questions"]
    i = data["q_index"]
    if i < len(questions):
        await state.set_state(BizScreening.question)
        return await message.answer(questions[i])
    await state.set_state(BizScreening.resume)
    await message.answer("Спасибо! И последнее — пришлите, пожалуйста, резюме файлом "
                         "(PDF, DOCX или TXT) или текстом. Если резюме нет, напишите «нет».")


@router.business_message(BizScreening.question, F.text)
async def got_answer(message: Message, state: FSMContext, store: Store):
    data = await state.get_data()
    questions = store.get_vacancy(data["vacancy_id"])["questions"]
    answers = data["answers"] + [{"question": questions[data["q_index"]], "answer": message.text.strip()}]
    await state.update_data(answers=answers, q_index=data["q_index"] + 1)
    await _ask_next(message, state, store)


@router.business_message(BizScreening.resume, F.document)
async def got_resume_file(message: Message, state: FSMContext, store: Store, bot: Bot):
    try:
        text = await read_resume(message)
    except ValueError as e:
        return await message.answer(f"{e}. Попробуйте другой файл или пришлите текстом.")
    await _finish(message, state, store, bot, text, message.document.file_name)


@router.business_message(BizScreening.resume, F.text)
async def got_resume_text(message: Message, state: FSMContext, store: Store, bot: Bot):
    text = "" if message.text.strip().lower() in NO_RESUME else message.text
    await _finish(message, state, store, bot, text, None)


async def _finish(message: Message, state: FSMContext, store: Store, bot: Bot,
                  resume_text: str, filename: str | None):
    data = await state.get_data()
    await state.set_state(BizScreening.done)
    await message.answer("Спасибо! Всё посмотрю и вернусь с ответом в ближайшее время 🙌")
    connection = await _connection(bot, message.business_connection_id)
    await submit_application(bot, store, data, message.from_user, resume_text, filename,
                             notify_chat_ids=(connection.user_chat_id,))


@router.business_message(~StateFilter(None))
async def need_text(message: Message):
    await message.answer("Ответьте, пожалуйста, текстом 🙂")
