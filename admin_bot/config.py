from shared.config import BaseConfig


class AdminBotConfig(BaseConfig):
    def __init__(self):
        super().__init__()
        self._bot_token = self._config_data.get("admin_bot_token")
        self._default_locale = self._config_data.get("admin_bot_default_locale", "ru")
        self._session_name = self._config_data.get("admin_session_name", "admin")

    @property
    def bot_token(self) -> str:
        token = self._bot_token
        if not token:
            raise ValueError("admin_bot_token is missing in config.json")
        return str(token)

    @property
    def default_locale(self) -> str:
        locale = str(self._default_locale or "ru")
        if locale not in {"ru", "en"}:
            return "ru"
        return locale

    @property
    def session_name(self) -> str:
        """Return absolute path to session file in project root."""
        return str(self.project_root / self._session_name)


config = AdminBotConfig()
