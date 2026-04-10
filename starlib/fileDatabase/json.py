import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("star")

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | dict[str, "JsonValue"] | list["JsonValue"]


class JsonContentModel(BaseModel):
    """Base model that keeps dict-like access for backward compatibility."""

    model_config = ConfigDict(extra="allow")

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "JsonContentModel":
        return cls.model_validate(dict(value or {}))

    def to_dict(self) -> dict[str, JsonValue]:
        dumped = self.model_dump(by_alias=True, exclude_none=True)
        return cast(dict[str, JsonValue], dumped)

    def __getitem__(self, key: str) -> JsonValue:
        return self.to_dict()[key]

    def __setitem__(self, key: str, value: JsonValue) -> None:
        setattr(self, key, value)

    def __contains__(self, key: object) -> bool:
        return key in self.to_dict()

    def get(self, key: str, default: object = None) -> JsonValue | object:
        return self.to_dict().get(key, default)

    def items(self):
        return self.to_dict().items()

    def keys(self):
        return self.to_dict().keys()

    def values(self):
        return self.to_dict().values()

    def update(self, value: Mapping[str, JsonValue]) -> None:
        for k, v in value.items():
            setattr(self, k, v)


class LocaleTextModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    en_us: str | None = Field(default=None, alias="en-US")
    zh_tw: str | None = Field(default=None, alias="zh-TW")


class JsonJdictModel(JsonContentModel):
    ApexMap: dict[str, str] = Field(default_factory=dict)
    ApexEvent: dict[str, str] = Field(default_factory=dict)
    ApexCraftingItem: dict[str, str] = Field(default_factory=dict)
    permissions: dict[str, str] = Field(default_factory=dict)
    rpgitem_category: dict[str, str] = Field(default_factory=dict)
    rpgequipment_solt: dict[str, str] = Field(default_factory=dict)
    warning_type: dict[str, str] = Field(default_factory=dict)


class JsonLolDictModel(JsonContentModel):
    champion: dict[str, str] = Field(default_factory=dict)
    road: dict[str, str] = Field(default_factory=dict)
    mod: dict[str, str] = Field(default_factory=dict)
    type: dict[str, str] = Field(default_factory=dict)
    map: dict[str, str] = Field(default_factory=dict)
    summoner_spell: dict[str, str] = Field(default_factory=dict)
    runes: dict[str, str] = Field(default_factory=dict)


class JsonPictureModel(JsonContentModel):
    radio_001: str
    lottery_001: str
    twitch_001: str
    dice_001: str


class JsonOptionsModel(JsonContentModel):
    channel_set_option: dict[str, LocaleTextModel] = Field(default_factory=dict)
    game_set_option: dict[str, LocaleTextModel] = Field(default_factory=dict)
    bet_option: dict[str, LocaleTextModel] = Field(default_factory=dict)
    pet_option: dict[str, LocaleTextModel] = Field(default_factory=dict)
    info_option: dict[str, LocaleTextModel] = Field(default_factory=dict)
    help_option: dict[str, LocaleTextModel] = Field(default_factory=dict)
    position_option: dict[str, LocaleTextModel] = Field(default_factory=dict)
    party_option: dict[str, LocaleTextModel] = Field(default_factory=dict)
    twitch_notify_option: dict[str, LocaleTextModel] = Field(default_factory=dict)


class JsonCommandNamesModel(JsonContentModel):
    commands: dict[str, LocaleTextModel] = Field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "JsonCommandNamesModel":
        source = dict(value or {})
        commands: dict[str, LocaleTextModel] = {}
        for key, raw in source.items():
            if isinstance(raw, dict):
                commands[key] = LocaleTextModel.model_validate(raw)
        return cls(commands=commands)

    def to_dict(self) -> dict[str, JsonValue]:
        dumped = {key: model.model_dump(by_alias=True, exclude_none=True) for key, model in self.commands.items()}
        return cast(dict[str, JsonValue], dumped)


class JsonDatabase:
    if TYPE_CHECKING:
        lol_jdict: JsonLolDictModel
        jdict: JsonJdictModel
        picdata: JsonPictureModel
        options: JsonOptionsModel
        cmd_names: JsonCommandNamesModel

    __slots__ = [
        "lol_jdict",
        "jdict",
        "picdata",
        "options",
        "cmd_names",
    ]

    _DBPATH = Path("./database")
    _PATH_DICT = {
        "lol_jdict": _DBPATH / "lol_dict.json",
        "jdict": _DBPATH / "dict.json",
        "picdata": _DBPATH / "picture.json",
        "options": _DBPATH / "command_option.json",
        "cmd_names": _DBPATH / "command_name.json",
    }

    _MODEL_DICT = {
        "lol_jdict": JsonLolDictModel,
        "jdict": JsonJdictModel,
        "picdata": JsonPictureModel,
        "options": JsonOptionsModel,
        "cmd_names": JsonCommandNamesModel,
    }

    def __init__(self, create_file=True):
        # create folder
        if not self._DBPATH.exists():
            self._DBPATH.mkdir(parents=True, exist_ok=True)
            logger.info(">> Created folder: %s <<", self._DBPATH)

        for file, path in self._PATH_DICT.items():
            if not path.exists():
                if not create_file:
                    continue
                with path.open("w", encoding="utf-8") as jfile:
                    json.dump({}, jfile, indent=4)
                    logger.info(">> Created json file: %s <<", file)

            with path.open(mode="r", encoding="utf8") as jfile:
                model_cls = self._MODEL_DICT[file]
                setattr(self, file, model_cls.from_mapping(json.load(jfile)))

    def write(self, file_name: str, data: dict | JsonContentModel):
        """
        Writes the given data to the specified file in the JSON.

        Args:
            file_name (str): The name of the file to write the data to.
            data (dict): The data to be written to the file.

        Raises:
            KeyError: If the specified file_name is not found in the JSON.
        """
        try:
            location = self._PATH_DICT[file_name]
            model_cls = self._MODEL_DICT[file_name]
            model_data = data if isinstance(data, JsonContentModel) else model_cls.from_mapping(data)
            setattr(self, file_name, model_data)
            with location.open(mode="w", encoding="utf8") as jfile:
                json.dump(model_data.to_dict(), jfile, indent=4, ensure_ascii=False)
        except KeyError as e:
            raise KeyError("此項目沒有在資料庫中") from e

    def get_picture(self, pic_key: str) -> str:
        """取得圖片網址"""
        return str(self.picdata[pic_key])

    def get_jdict(self, key: str, value: str) -> str:
        """取得jdict資料"""
        item = self.jdict.get(key, {})
        if isinstance(item, dict):
            return str(item.get(value, value))
        return value

    def get_tw(self, value, option_name: str) -> str:
        """
        Retrieve the Traditional Chinese (zh-TW) translation for a given value and option name.
        Args:
            value (T): The value to be translated.
            option_name (str): The name of the option to look up in the dictionary.
        Returns:
            str | T: The translated value if found, otherwise the original value.
        """
        jdict_item = self.jdict.get(option_name)
        if isinstance(jdict_item, dict):
            zh_tw = jdict_item.get("zh-TW")
            if isinstance(zh_tw, dict):
                return str(zh_tw.get(str(value), value))
            return str(jdict_item.get(str(value), value))

        option_item = self.options.get(option_name)
        if isinstance(option_item, dict):
            localized = option_item.get(str(value))
            if isinstance(localized, dict):
                return str(localized.get("zh-TW", value))

        return str(value)
