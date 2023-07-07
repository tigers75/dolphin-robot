import logging
from os import path, remove

from cryptography.fernet import Fernet

from homeassistant.config_entries import STORAGE_VERSION, ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.json import JSONEncoder
from homeassistant.helpers.storage import Store

from ..common.consts import (
    DEFAULT_NAME,
    DOMAIN,
    LEGACY_KEY_FILE,
    STORAGE_DATA_AWS_TOKEN_ENCRYPTED_KEY,
    STORAGE_DATA_KEY,
    STORAGE_DATA_LOCATING,
)

_LOGGER = logging.getLogger(__name__)


class ConfigManager:
    _encryption_key: str | None
    _crypto: Fernet | None
    _store: Store | None
    _data: dict | None

    _password: str | None

    def __init__(self, hass: HomeAssistant | None, entry: ConfigEntry | None = None):
        self._hass = hass
        self._encryption_key = None
        self._crypto = None
        self._store = None

        self._data = None

        self._password = None

        self._entry_data = None
        self._store_data = None

        if entry is None:
            self._entry_data = {}
            self._entry_title = DEFAULT_NAME
            self._entry_id = "config"
            self._store = None

        else:
            self._entry_data = entry.data
            self._entry_title = entry.title
            self._entry_id = entry.entry_id

            file_name = f"{DOMAIN}.{self._entry_id}.config.json"

            self._store = Store(hass, STORAGE_VERSION, file_name, encoder=JSONEncoder)

    @property
    def data(self):
        return self._data

    @property
    def name(self):
        entry_title = self._entry_title

        return entry_title

    @property
    def is_locating(self) -> bool:
        is_locating = self.data.get(STORAGE_DATA_LOCATING, False)

        return is_locating

    @property
    def username(self) -> str:
        username = self.data.get(CONF_USERNAME)

        return username

    @property
    def password_hashed(self) -> str:
        password_hashed = self._encrypt(self.password)

        return password_hashed

    @property
    def password(self) -> str:
        password = self.data.get(CONF_PASSWORD)

        return password

    @property
    def aws_token_encrypted_key(self) -> str | None:
        key = self.data.get(STORAGE_DATA_AWS_TOKEN_ENCRYPTED_KEY)

        return key

    async def initialize(self):
        await self._load()

        password_hashed = self._entry_data.get(CONF_PASSWORD)
        password = None

        if password_hashed is not None:
            password = self._decrypt(password_hashed)

        self.data[CONF_USERNAME] = self._entry_data.get(CONF_USERNAME)
        self.data[CONF_PASSWORD] = password

    def update_credentials(self, data: dict):
        self._entry_data = data

    async def update_aws_token_encrypted_key(self, key: str):
        self.data[STORAGE_DATA_AWS_TOKEN_ENCRYPTED_KEY] = key

        await self._save()

    async def update_is_locating(self, state: bool):
        self.data[STORAGE_DATA_LOCATING] = state

        await self._save()

    async def _load(self):
        self._data = None

        await self._load_config_from_file()
        await self._load_encryption_key()

        if self._data is None:
            self._data = {
                STORAGE_DATA_LOCATING: False,
                STORAGE_DATA_AWS_TOKEN_ENCRYPTED_KEY: None,
                STORAGE_DATA_KEY: self._encryption_key,
            }

            await self._save()

    async def _load_config_from_file(self):
        if self._store is not None:
            self._store_data = await self._store.async_load()

            if self._store_data is not None:
                self._data = self._store_data.get(self._entry_id)

    async def _load_encryption_key(self):
        if self._data is None:
            if self._hass is not None:
                await self._import_encryption_key()

        else:
            self._encryption_key = self._data.get(STORAGE_DATA_KEY)

        if self._encryption_key is None:
            self._encryption_key = Fernet.generate_key().decode("utf-8")

        self._crypto = Fernet(self._encryption_key.encode())

    async def _import_encryption_key(self):
        """Load the retained data from store and return de-serialized data."""
        key = None

        legacy_key_path = self._hass.config.path(LEGACY_KEY_FILE)

        if path.exists(legacy_key_path):
            with open(legacy_key_path, "rb") as file:
                key = file.read().decode("utf-8")

            remove(legacy_key_path)

        else:
            store = Store(
                self._hass, STORAGE_VERSION, f".{DOMAIN}", encoder=JSONEncoder
            )

            data = await store.async_load()

            if data is not None:
                key = data.get("key")

                await store.async_remove()

        if key is not None:
            self._encryption_key = key

    async def _save(self):
        if self._store is None:
            return

        if self._entry_id not in self._store_data:
            self._store_data[self._entry_id] = {}

        for key in self._data:
            if key not in [CONF_PASSWORD, CONF_USERNAME]:
                self._store_data[self._entry_id][key] = self._data[key]

        await self._store.async_save(self._store_data)

    def _encrypt(self, data: str) -> str:
        if data is not None:
            data = self._crypto.encrypt(data.encode()).decode()

        return data

    def _decrypt(self, data: str) -> str:
        if data is not None and len(data) > 0:
            data = self._crypto.decrypt(data.encode()).decode()

        return data
