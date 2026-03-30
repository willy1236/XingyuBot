import json
import shutil
import subprocess
from collections.abc import Iterator
from datetime import timezone
from typing import TypeVar

import feedparser
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from starlib.database import APIType, sqldb
from starlib.exceptions import APINetworkError, Forbidden
from starlib.settings import tz
from starlib.utils import log

from ..base import APICaller
from .models import *

T = TypeVar("T")


class TwitchAPI(APICaller):
    """
    與Twitch api交互相關
    """

    base_url = "https://api.twitch.tv/helix"

    def __init__(self):
        super().__init__()
        self.headers = self.__get_headers()

    def __get_headers(self):
        TOKENURL = "https://id.twitch.tv/oauth2/token"
        # headers = {"Content-Type": "application/x-www-form-urlencoded"}
        tokens = sqldb.get_identifier_secret(APIType.Twitch)
        params = {"client_id": tokens.client_id, "client_secret": tokens.client_secret, "grant_type": "client_credentials"}

        r = self._request("POST", TOKENURL, params=params)
        apidata = r.json()
        headers = {"Authorization": f"Bearer {apidata['access_token']}", "Client-Id": tokens.client_id}
        return headers

    def _build_request(self, endpoint: str, params: dict, model: T) -> Iterator[T]:
        after = True
        while after:
            r = self.get(endpoint, params=params)
            apidata = r.json()
            if apidata.get("pagination"):
                after = apidata["pagination"].get("cursor")
                params["after"] = after
            else:
                after = None

            for i in apidata["data"]:
                yield model(**i)

    def get_lives(self, users: str | list[str], use_user_logins=False) -> dict[str, TwitchStream | None]:
        """
        取得twitch用戶的直播資訊
        :param users: list of users id
        :return: dict: {user_id: TwitchStream | None（如果無正在直播）}
        """
        params = {"first": 100}
        if use_user_logins:
            params["user_login"] = users
        else:
            params["user_id"] = users
        r = self.get("streams", params=params)
        apidata = r.json()
        dct = {}

        if not isinstance(users, list):
            users = [users]

        for user in users:
            dct[user] = None

        for data in apidata["data"]:
            if use_user_logins:
                dct[data.get("user_login")] = TwitchStream(**data)
            else:
                dct[data.get("user_id")] = TwitchStream(**data)

        return dct

    def get_user(self, username: str) -> TwitchUser | None:
        """
        取得Twitch用戶
        :param username: 用戶名稱（user_login）
        """
        params = {"login": username, "first": 1}
        r = self.get("users", params=params)
        apidata = r.json()
        if apidata.get("data"):
            return TwitchUser(**apidata["data"][0])
        else:
            return None

    def get_user_test(self, username: str):
        params = {"login": username, "first": 1}
        gen = self._build_request("users", params, TwitchUser)
        data = next(gen)
        print(data)
        if data:
            return TwitchUser(**data)
        else:
            return None

    def get_user_by_id(self, userid: str) -> TwitchUser | None:
        """
        取得Twitch用戶
        :param userid: 用戶id（user_id）
        """
        params = {"id": userid, "first": 1}
        r = self.get("users", params=params)
        apidata = r.json()
        if apidata.get("data"):
            return TwitchUser(**apidata["data"][0])
        else:
            return None

    def get_videos(self, user_ids: str | list[str] = None, video_ids: str | list[str] = None, types: str | list[str] = "highlight", after: datetime = None) -> list[TwitchVideo] | None:
        """
        取得twitch用戶的影片資訊
        :param user_ids: list of users id
        :return: list[TwitchVideo]
        """
        params = {"sort": "time", "first": 5, "type": types}

        if user_ids:
            params["user_id"] = user_ids
        elif video_ids:
            params["id"] = video_ids
        else:
            raise ValueError("must provide either user_ids or video_ids.")

        r = self.get("videos", params=params)
        apidata = r.json()
        if apidata.get("data"):
            results = [TwitchVideo(**i) for i in apidata["data"]]
            if after:
                results = [i for i in results if i.created_at > after]
            return results
        else:
            return None

    def get_clips(self, broadcaster_id: str, started_at: datetime | None = None):
        """
        取得twitch用戶的剪輯資訊\\
        *即使加入了started_at參數，Twitch API也會返回指定時間之前的clip，原因未知，需手動過濾資料*
        """
        params = {
            "broadcaster_id": broadcaster_id,
            "first": 5,
        }
        if started_at:
            params["started_at"] = started_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            params["ended_at"] = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        r = self.get("clips", params=params)
        apidata = r.json()
        if apidata.get("data"):
            if started_at:
                return [clip for clip in [TwitchClip(**i) for i in apidata["data"]] if clip.created_at > started_at]
            else:
                return [TwitchClip(**i) for i in apidata["data"]]
        else:
            return None


class GoogleAPI(APICaller):
    """無身分驗證的Google API"""

    base_url = "https://www.googleapis.com/youtube/v3"

    def __init__(self):
        self.__token = sqldb.get_access_token(APIType.Google).access_token
        super().__init__(headers={"x-goog-api-key": self.__token, "Accept": "application/json"})

    def get_channel_id(self, channel_handle: str) -> str | None:
        """
        Retrieves the channel ID for a given channel handle.

        Args:
            channel_handle (str): The handle of the channel.

        Returns:
            str | None: The ID of the channel if found, None otherwise.
        """
        params = {"forHandle": channel_handle, "part": "id", "maxResults": 1}
        data = self.get("channels", params=params).json()
        if data["pageInfo"]["totalResults"]:
            return data["items"][0]["id"]
        return None

    def get_channel(self, channel_id: str = None, handle: str = None):
        """獲取Youtube頻道資訊
        :param id: 頻道ID
        :param handle: 頻道名稱
        兩者擇一提供即可
        """
        params = {"id": channel_id, "forHandle": handle, "part": "statistics,snippet", "maxResults": 1}
        data = self.get("channels", params=params).json()
        return YoutubeChannel(**data.get("items")[0]) if data.get("items") else None

    def get_channelsection(self, channel_id: str):
        params = {"key": self.__token, "channelId": channel_id, "part": "contentDetails"}
        r = self.get("channelSections", params=params)
        print(r)
        print(r.json())

    def get_streams(self, channel_ids: list):
        print(",".join(channel_ids))
        params = {"key": self.__token, "part": "snippet", "channelId": ",".join(channel_ids), "eventType": "live", "type": "video"}
        r = self.get("search", params=params)
        print(r)
        print(r.json())

    def get_stream(self, channel_id: str):
        """取得Youtube直播資訊（若無正在直播則回傳None）"""
        params = {"part": "snippet", "channelId": channel_id, "eventType": "live", "type": "video"}
        data = self.get("search", params=params).json()
        return YouTubeStream(**data["items"][0]) if data["items"] else None

    def get_video(self, video_id: str | list) -> list[YoutubeVideo]:
        params = {"part": "snippet,liveStreamingDetails", "id": video_id}
        data = self.get("videos", params=params).json()
        return [YoutubeVideo(**i) for i in data["items"]] if data["items"] else list()

    def get_playlist(self, playlist_id: str | list):
        params = {"key": self.__token, "part": "snippet,contentDetails", "id": playlist_id}
        data = self.get("playlists", params=params).json()
        return data["items"][0] if data["items"] else None

    def get_playlist_item(self, playlist_id: str | list):
        params = {"key": self.__token, "part": "snippet,contentDetails", "playlistId": playlist_id}
        data = self.get("playlistItems", params=params).json()
        return data["items"][0] if data["items"] else None


class YoutubeRSS:
    def get_videos(self, channel_id, after: datetime | None = None) -> list[YoutubeRSSVideo]:
        """從RSS取得影片（由新到舊）"""
        feed = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}")
        results = [YoutubeRSSVideo(**i) for i in feed["entries"]]
        if after:
            return [i for i in results if i.uplood_at > after]
        else:
            return results


class YoutubePush(APICaller):
    base_url = "https://pubsubhubbub.appspot.com"

    def __init__(self):
        super().__init__()

    def add_push(self, channel_id: str, callback_url: str, secret: str = None):
        try:
            data = {
                "hub.callback": callback_url,
                "hub.topic": f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}",
                "hub.verify": "async",
                "hub.mode": "subscribe",
                "hub.verify_token": None,
                "hub.secret": secret,
                "hub.lease_numbers": None,
            }
            header = {"Content-Type": "application/x-www-form-urlencoded"}
            self._request("POST", "subscribe", data=data, headers=header)
        except Exception as e:
            log.exception("Args: %a %s %s", channel_id, callback_url, secret)

    def get_push(self, channel_id: str, callback_url: str, secret: str = None):
        params = {"hub.callback": callback_url, "hub.topic": f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}", "hub.secret": secret}
        r = self.get("subscription-details", params=params)
        return self._parse_subscription_details(r.text)

    @staticmethod
    def _parse_subscription_details(html_content: str) -> YtSubscriptionDetails:
        soup = BeautifulSoup(html_content, "html.parser")

        def get_text_from_dt(dt_text: str) -> str:
            dt = soup.find("dt", string=dt_text)
            if dt and dt.find_next_sibling("dd"):
                return dt.find_next_sibling("dd").get_text(strip=True)
            return "n/a"

        def parse_datetime(dt_text: str) -> datetime | None:
            """
            將時間字串轉換為 datetime，如果為 'n/a' 則返回 None。
            """
            time_str = get_text_from_dt(dt_text)
            time_str = time_str.split(sep="\n", maxsplit=1)[0]
            if time_str.strip().lower() == "n/a":
                return None
            try:
                return datetime.strptime(time_str, "%a, %d %b %Y %H:%M:%S %z").astimezone(tz=tz)
            except ValueError as e:
                log.error("時間格式錯誤: %s，原始時間字串: %s，欄位: %s", e, time_str, dt_text)
                return None

        return YtSubscriptionDetails(
            callback_url=get_text_from_dt("Callback URL"),
            state=get_text_from_dt("State"),
            last_successful_verification=parse_datetime("Last successful verification"),
            expiration_time=parse_datetime("Expiration time"),
            last_subscribe_request=parse_datetime("Last subscribe request"),
            last_unsubscribe_request=parse_datetime("Last unsubscribe request"),
            last_verification_error=parse_datetime("Last verification error"),
            last_delivery_error=parse_datetime("Last delivery error"),
            last_item_delivered=get_text_from_dt("Last item delivered"),
            aggregate_statistics=get_text_from_dt("Aggregate statistics"),
            content_received=parse_datetime("Content received"),
            content_delivered=parse_datetime("Content delivered"),
        )


class XingyuGoogleCloud:
    """以星羽身分運行的Google Cloud API"""

    def __init__(self):
        self.creds = self.get_creds()

    def get_creds(self):
        # If modifying these scopes, delete the file token.json.
        SCOPES = ["https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/drive"]
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        creds = sqldb.get_google_credentials(SCOPES)
        # if os.path.exists('database/google_token.json'):
        #     creds = Credentials.from_authorized_user_file('database/google_token.json', SCOPES)

        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            token = sqldb.get_bot_oauth_token(APIType.Google, 2)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                client_config = sqldb.get_google_client_config()
                flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
                # flow = InstalledAppFlow.from_client_secrets_file(
                #     'database/credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            # with open('database/google_token.json', 'w', encoding="utf-8") as token:
            #     token.write(creds.to_json())
            token.access_token = creds.token
            token.refresh_token = creds.refresh_token
            token.expires_at = creds.expiry
            sqldb.merge(token)

        return creds

    def get_me(self):
        service = build("oauth2", "v2", credentials=self.creds)
        user_info = service.userinfo().get().execute()
        return user_info

    def list_drive_files(self):
        """Shows basic usage of the Drive v3 API.
        Prints the names and ids of the first 10 files the user has access to.
        """

        try:
            service = build("drive", "v3", credentials=self.creds)

            # Call the Drive v3 API
            results = service.files().list(pageSize=10, fields="nextPageToken, files(id, name)").execute()
            items = results.get("files", [])

            if not items:
                print("No files found.")
                return
            print("Files:")
            for item in items:
                print(f"{item['name']} ({item['id']})")
            return results
        except HttpError as error:
            print(f"An error occurred: {error}")

    def list_file_permissions(self, fileId):
        service = build("drive", "v3", credentials=self.creds)
        results = service.permissions().list(fileId=fileId, fields="permissions(*)").execute()
        return results

    def add_file_permissions(self, fileId, emailAddress):
        service = build("drive", "v3", credentials=self.creds)
        permission_dict = {"role": "reader", "type": "user", "emailAddress": emailAddress}
        results = service.permissions().create(fileId=fileId, body=permission_dict).execute()
        return results

    def remove_file_permissions(self, fileId, permissionId):
        service = build("drive", "v3", credentials=self.creds)
        results = service.permissions().delete(fileId=fileId, permissionId=permissionId).execute()
        return results


class NotionAPI(APICaller):
    base_url = "https://api.notion.com/v1"

    def __init__(self):
        super().__init__(headers=self._get_headers())

    def _get_headers(self):
        token = sqldb.get_access_token(APIType.Notion).access_token
        return {"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}

    def get_page(self, page_id: str):
        r = self.get(f"pages/{page_id}")
        apidata = r.json()
        return NotionPage(**apidata)

    def get_page_property(self, page_id: str, property_id: str):
        r = self.get(f"pages/{page_id}/properties/{property_id}")
        apidata = r.json()
        return apidata

    def add_page(self, data: dict, database_id: str | None = None):
        """新增Notion資料庫項目"""
        if database_id is not None:
            data["parent"] = {"database_id": database_id}
        r = self.post("pages", data=data)
        apidata = r.json()
        return NotionPage(**apidata)

    def update_page(self, page_id: str, data: dict):
        """更新Notion頁面"""
        r = self.patch(f"pages/{page_id}", data=data)
        apidata = r.json()
        return NotionPage(**apidata)

    def get_block(self, block_id: str):
        r = self.get(f"blocks/{block_id}")
        apidata = r.json()
        return NotionBlock(**apidata)

    def get_block_children(self, block_or_page_id: str):
        r = self.get(f"blocks/{block_or_page_id}/children")
        apidata = r.json()
        return NotionQueryResponse(**apidata)

    def update_block(self, block_id: str, data: dict):
        """更新Notion區塊內容"""
        r = self.patch(f"blocks/{block_id}", data=data)
        apidata = r.json()
        if apidata["object"] == "list":
            return [NotionBlock(**i) for i in apidata["results"]]
        else:
            return NotionBlock(**apidata)

    def delete_block(self, block_or_page_id: str):
        """刪除Notion區塊或頁面"""
        r = self.delete(f"blocks/{block_or_page_id}")
        apidata = r.json()
        return NotionBlock(**apidata)

    def search(self, title: str, page_size=100):
        """search by title"""
        data = {"query": title, "page_size": page_size}
        r = self.post("search", data=data)
        apidata = r.json()
        try:
            return NotionQueryResponse(**apidata)
        except Exception as e:
            print(f"解析 Notion 搜尋結果時發生錯誤: {e}")
            print(f"原始數據: {apidata}")
            return None

    def get_database(self, database_id: str):
        """取得Notion資料庫"""
        r = self.get(f"databases/{database_id}")
        apidata = r.json()
        return NotionDatabase(**apidata)

    def add_page_title_content(self, title: str, content: str, database_id: str):
        """新增Notion資料庫項目，僅設定標題與內容"""
        data = {
            "parent": {"database_id": database_id},
            "properties": {"名稱": NotionPropertyValue(id="title", type="title", title=[NotionRichText(type="text", text=NotionRichTextContent(content=title), plain_text=title)]).model_dump(exclude_none=True)},
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [NotionRichText(type="text", text=NotionRichTextContent(content=content)).model_dump(exclude_none=True)]},
                }
            ],
        }

        r = self.post("pages", data=data)
        apidata = r.json()
        return NotionPage(**apidata)

    def update_page_content(self, page_id: str, content: str):
        """更新Notion頁面內容"""
        data = {
            "paragraph": {"rich_text": [NotionRichText(type="text", text=NotionRichTextContent(content=content)).model_dump(exclude_none=True)]},
        }
        blocks = self.get_block_children(page_id)
        return self.update_block(blocks.results[0].id, data)


class RssHub(APICaller):
    base_url = "https://rsshub.app"

    def __init__(self):
        self.url_local = "http://localhost:1200"
        super().__init__()

    def get_twitter(self, username: str, local=False, after: datetime | None = None):
        """取得Twitter用戶的RSS"""
        # * api不支援id查詢 故使用username查詢
        if local:
            try:
                r = self.get(f"twitter/user/{username}", base_url=self.url_local)
            except APINetworkError:
                r = self.get(f"twitter/user/{username}")
        else:
            r = self.get(f"twitter/user/{username}")

        feeds = feedparser.parse(r.text)
        results = [RssHubTwitterTweet(**feed) for feed in feeds.entries]
        results.reverse()

        if after:
            return [result for result in results if result.published_parsed > after]
        else:
            return results


class CLIInterface:
    # TODO: 針對rettiwt指令列介面進行全面測試
    def __init__(self):
        self.rettiwt_api_key = sqldb.get_access_token(APIType.Rettiwt).access_token
        if shutil.which("rettiwt") is None:
            log.warning("找不到rettiwt執行檔，請確認是否已安裝rettiwt並將其加入系統PATH中")

    def get_user_timeline(self, user_id: str, after: datetime | None = None) -> RettiwtTweetTimeLineResponse | None:
        r = subprocess.run(f'rettiwt -k "{self.rettiwt_api_key}" user timeline "{user_id}" 10', shell=True, capture_output=True, encoding="utf-8", check=False)
        r.check_returncode()
        data = json.loads(r.stdout)

        try:
            results = RettiwtTweetTimeLineResponse(**data)
        except Exception as e:
            log.exception("解析Rettiwt輸出時發生錯誤，輸出內容：%s", r.stdout)
            return None

        if after:
            results.list = [i for i in results.list if i.createdAt > after and i.tweetBy.id == user_id]
        else:
            results.list = [i for i in results.list if i.tweetBy.id == user_id]
        return results

    def get_user_details(self, user_id_or_name: str) -> RettiwtTweetUser | None:
        r = subprocess.run(
            f'rettiwt -k "{self.rettiwt_api_key}" user details "{user_id_or_name.removeprefix("@")}"',
            shell=True,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )
        r.check_returncode()
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError:
            log.exception("get_user_details 解析JSON失敗，輸出內容：%s", r.stdout)
            return None

        if not data or data.get("name") == "VALIDATION_ERROR":
            return None

        return RettiwtTweetUser(**data)

    def get_tweet_details(self, tweet_id: str) -> RettiwtTweetItem | None:
        r = subprocess.run(f'rettiwt -k "{self.rettiwt_api_key}" tweet details "{tweet_id}"', shell=True, capture_output=True, encoding="utf-8", check=False)
        r.check_returncode()
        data = json.loads(r.stdout)

        if data.get("name") == "VALIDATION_ERROR":
            return None

        return RettiwtTweetItem(**data)
