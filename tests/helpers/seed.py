"""暫時資料庫的 session 層級準備：補建表、寫入 import 時與測試會讀的 API 憑證（全部是假值），再 import `starlib.instance`。

結構照本機 DB 的 credentials schema：每組 (APIType, source_seq) 一列 Credential，底下掛該型別的 token 表。
"""

from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session

from starlib.database import (
    AccessToken,
    APIType,
    Credential,
    CredentialType,
    IdentifierSecret,
    OAuthClient,
    WebSubConfig,
)
from starlib.database.postgresql.client import SQLRepository
from starlib.database.postgresql.schemas import Base

# (來源, seq, 型別, 讀它的地方)
_CREDENTIALS = [
    # starlib.instance 在 import 時建立的 API client
    (APIType.MCSS, 1, CredentialType.Bearer_Token, "McssAPI"),
    (APIType.MCSMANAGER, 1, CredentialType.Bearer_Token, "McsManagerAPI"),
    (APIType.Google, 1, CredentialType.Bearer_Token, "GoogleAPI"),
    (APIType.Twitch, 1, CredentialType.Id_Secret, "TwitchAPI"),
    (APIType.Twitter, 1, CredentialType.Bearer_Token, "instance.twitter_api"),
    (APIType.CWA, 1, CredentialType.Bearer_Token, "CWA_API"),
    (APIType.ApexStatue, 1, CredentialType.Bearer_Token, "ApexAPI"),
    (APIType.Rettiwt, 1, CredentialType.Bearer_Token, "CLIInterface"),
    # starServer.bot_website 在 import 時讀的設定
    (APIType.Discord, 4, CredentialType.Oauth2, "bot_website／後台 Discord 登入"),
    (APIType.DocAccount, 1, CredentialType.Id_Secret, "bot_website.docs_account"),
    (APIType.Google, 4, CredentialType.WebSub, "bot_website.websub_config"),
    (APIType.Line, 1, CredentialType.LineBot, "bot_website LINE webhook"),
    (APIType.Google, 5, CredentialType.Bearer_Token, "starAgent_line（bot_website import）"),
    # starDiscord.cmds.system_game 在 import 時建立的 client
    (APIType.Riot, 1, CredentialType.Bearer_Token, "system_game.riot_api"),
    # 測試與 twitch_tokens 讀的實況主授權 client
    (APIType.Twitch, 3, CredentialType.Oauth2, "twitch_tokens.BROADCASTER_CLIENT_SEQ"),
]


def _rows(credential_id: int, source: APIType, seq: int, kind: CredentialType) -> list:
    secret = f"test-{source.name.lower()}-{seq}"
    if kind == CredentialType.Bearer_Token:
        return [AccessToken(credential_id=credential_id, access_token=secret, expires_at=None)]
    if kind == CredentialType.Id_Secret:
        return [IdentifierSecret(credential_id=credential_id, client_id=f"{secret}-id", client_secret=secret)]
    if kind == CredentialType.LineBot:
        return [
            AccessToken(credential_id=credential_id, access_token=secret, expires_at=None),
            IdentifierSecret(credential_id=credential_id, client_id=f"{secret}-id", client_secret=secret),
        ]
    if kind == CredentialType.Oauth2:
        return [
            OAuthClient(
                credential_id=credential_id,
                client_id=f"{secret}-id",
                client_secret=secret,
                redirect_uri=f"https://api.example.test/oauth/{source.name.lower()}",
                default_scopes=[],
            )
        ]
    if kind == CredentialType.WebSub:
        return [WebSubConfig(credential_id=credential_id, callback_uri="https://api.example.test/websub")]
    raise ValueError(kind)


def prepare(repo: SQLRepository) -> None:
    """`create_sqldb` 只對 SQLModel.metadata 做 create_all；純 SQLAlchemy 的 `Base` 表在正式機是手動建的，這裡補建。"""
    Base.metadata.create_all(repo.engine)
    _seed(repo)
    _import_instance_offline()


def _seed(repo: SQLRepository) -> None:
    with Session(repo.engine) as session:
        for source, seq, kind, client_name in _CREDENTIALS:
            credential = Credential(type=kind, source=source, source_seq=seq, client_name=client_name)
            session.add(credential)
            session.flush()
            session.add_all(_rows(credential.id, source, seq, kind))
        session.commit()


def _import_instance_offline() -> None:
    """先 import `starlib.instance`：TwitchAPI 建構時會向 Twitch 換 app token，假憑證換不到，import 期間改回假 header。"""
    from starlib.providers.social.platforms import TwitchAPI

    with patch.object(TwitchAPI, "_TwitchAPI__get_headers", lambda self: {"Client-Id": "test-twitch-1-id"}):
        import starlib.instance  # noqa: F401


#: 選到 integration 測試時，從原 DB 唯讀複製的表（依外鍵順序），取代上面的假憑證。
#: 只複製 app 層級的憑證：credentials.credential／id_secret／access_token／oauth_client／websub_config；
#: oauth_token（各使用者的授權）與 websub_instance（執行期的訂閱狀態）不複製。
#: 限制：import 時就建好的 client（starlib.instance、bot_website 的模組變數）仍拿著假憑證，
#: 只有執行期才讀 DB 的地方（如 test_community 建立的 CLIInterface）會拿到真實憑證。
_REAL_CREDENTIAL_TABLES = [Credential, IdentifierSecret, AccessToken, OAuthClient, WebSubConfig]


def use_real_credentials(repo: SQLRepository, source: Engine) -> None:
    """把假憑證換成原 DB 的真實憑證；`source` 必須是唯讀連線，對原 DB 只做 SELECT。"""
    tables = [model.__table__ for model in _REAL_CREDENTIAL_TABLES]
    try:
        with source.connect() as src:
            rows = {table: [dict(row) for row in src.execute(table.select()).mappings()] for table in tables}
    finally:
        source.dispose()
    names = ", ".join(f'"{table.schema}"."{table.name}"' for table in tables)
    with repo.engine.begin() as dst:
        dst.execute(text(f"TRUNCATE {names} CASCADE"))
        for table in tables:
            if rows[table]:
                dst.execute(table.insert(), rows[table])
