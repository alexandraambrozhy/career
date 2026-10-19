"""Сценарий Telegram Business: кандидат пишет рекрутеру, бот отвечает от его имени."""
import asyncio
import datetime

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import GetBusinessConnection, SendMessage
from aiogram.types import BusinessBotRights, BusinessConnection, Chat, Message, Update, User

from app.bot import build_dispatcher
from app.db import Store

OWNER = User(id=1, is_bot=False, first_name="Рекрутер")
CANDIDATE = User(id=7, is_bot=False, first_name="Анна", username="anna")
FRIEND = User(id=8, is_bot=False, first_name="Петя")
NOW = datetime.datetime.now()
CONNECTION = BusinessConnection(id="bc1", user=OWNER, user_chat_id=1, date=NOW, is_enabled=True,
                                rights=BusinessBotRights(can_reply=True))
# роутеры модульные и подключаются к диспетчеру один раз; хранилище подменяем в каждом тесте
DP = build_dispatcher(store=None)


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent: list[SendMessage] = []

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):
        yield b""

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, GetBusinessConnection):
            return CONNECTION
        if isinstance(method, SendMessage):
            self.sent.append(method)
            return Message(message_id=len(self.sent), date=NOW, text=method.text,
                           chat=Chat(id=method.chat_id, type="private"))
        return True


def _run(store: Store, messages: list[tuple[User, int, str]]) -> FakeSession:
    session = FakeSession()
    bot = Bot("42:TEST", session=session)
    DP["store"] = store
    DP.fsm.storage = MemoryStorage()  # диалоги не должны переезжать между тестами

    async def feed():
        for i, (user, chat_id, text) in enumerate(messages, 1):
            msg = Message(message_id=i, date=NOW, chat=Chat(id=chat_id, type="private"),
                          from_user=user, text=text, business_connection_id="bc1")
            await DP.feed_update(bot, Update(update_id=i, business_message=msg))

    asyncio.run(feed())
    return session


def test_candidate_screened_on_behalf_of_recruiter(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    vid = store.create_vacancy("Менеджер по продажам", "B2B SaaS", "CRM, B2B, переговоры",
                               ["Сколько лет опыта в B2B?", "Работали в CRM?"], 50)
    session = _run(store, [
        (CANDIDATE, 7, "Здравствуйте, я по вакансии"), (CANDIDATE, 7, "да"),
        (CANDIDATE, 7, "Анна Смирнова"), (CANDIDATE, 7, "+79161234567"),
        (CANDIDATE, 7, "5 лет B2B"), (CANDIDATE, 7, "amoCRM, переговоры"), (CANDIDATE, 7, "нет"),
        (CANDIDATE, 7, "А когда ответ?"),  # после анкеты бот молчит, дальше — человек
    ])
    to_candidate = [m for m in session.sent if m.chat_id == 7]
    assert all(m.business_connection_id == "bc1" for m in to_candidate)
    assert [m.text for m in to_candidate[-4:-1]] == ["Сколько лет опыта в B2B?", "Работали в CRM?",
                                                     to_candidate[-2].text]
    assert to_candidate[-1].text.startswith("Спасибо! Всё посмотрю")
    assert any(m.chat_id == 1 and "Анна Смирнова" in m.text for m in session.sent)  # уведомление рекрутеру

    [cand] = store.list_candidates(vid)
    assert cand["contact"] == "+79161234567" and len(cand["answers"]) == 2 and cand["score"] >= 50


def test_bot_goes_silent_when_recruiter_replies(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    store.create_vacancy("Python-разработчик", "Бэкенд", "Python", [], 70)
    session = _run(store, [
        (FRIEND, 8, "Привет!"), (OWNER, 8, "Петя, привет, отвечу сама"), (FRIEND, 8, "да"),
    ])
    assert len(session.sent) == 1  # только первое приветствие
    assert store.is_paused("bc1", 8)


def test_no_vacancy_choice_needed_when_title_mentioned(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    store.create_vacancy("Python-разработчик", "Бэкенд", "Python", [], 70)
    store.create_vacancy("Дизайнер", "UI", "Figma", [], 70)
    session = _run(store, [(CANDIDATE, 7, "Добрый день! Интересует вакансия дизайнер")])
    assert "<b>Дизайнер</b>" in session.sent[0].text
