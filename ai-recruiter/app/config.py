import os
from dataclasses import dataclass, field


def _ids(raw: str) -> list[int]:
    return [int(x) for x in raw.replace(" ", "").split(",") if x]


@dataclass(frozen=True)
class Settings:
    telegram_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("CLAUDE_MODEL", "claude-opus-5-5"))
    # Telegram chat IDs, куда бот присылает подходящих кандидатов
    recruiter_chat_ids: list[int] = field(
        default_factory=lambda: _ids(os.getenv("RECRUITER_CHAT_IDS", ""))
    )
    admin_user: str = field(default_factory=lambda: os.getenv("ADMIN_USER", "admin"))
    admin_password: str = field(default_factory=lambda: os.getenv("ADMIN_PASSWORD", "admin"))
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "recruiter.db"))
    web_host: str = field(default_factory=lambda: os.getenv("WEB_HOST", "0.0.0.0"))
    web_port: int = field(default_factory=lambda: int(os.getenv("WEB_PORT", "8000")))
    # адрес панели для ссылок в уведомлениях
    public_url: str = field(
        default_factory=lambda: os.getenv("PUBLIC_URL", "http://localhost:8000").rstrip("/")
    )

    @property
    def demo_mode(self) -> bool:
        """Без ключа Anthropic скоринг работает на простой эвристике."""
        return not self.anthropic_api_key


settings = Settings()
