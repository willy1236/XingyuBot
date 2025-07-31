import json
import subprocess
from collections.abc import Iterator
from datetime import timezone
from typing import TypeVar

import feedparser
import requests
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..database import sqldb
from ..errors import APIInvokeError, Forbidden
from ..models.community import *
from ..settings import tz
from ..types import APIType
from ..utils import log

T = TypeVar("T")


class TwitchAPI:
    """
    與Twitch api交互相關
    """

    BaseURL = "https://api.twitch.tv/helix"

    def __init__(self):
        self._headers = None

    @property
    def headers(self):
        if self._headers is None:
            self._headers = self.__get_headers()
        return self._headers

    def __get_headers(self):
        TOKENURL = "https://id.twitch.tv/oauth2/token"
        # headers = {"Content-Type": "application/x-www-form-urlencoded"}
        tokens = sqldb.get_bot_token(APIType.Twitch)
        params = {"client_id": tokens.client_id, "client_secret": tokens.client_secret, "grant_type": "client_credentials"}

        r = requests.post(TOKENURL, params=params)
        apidata = r.json()
        if r.ok:
            headers = {"Authorization": f"Bearer {apidata['access_token']}", "Client-Id": tokens.client_id}
            return headers
        else:
            raise Forbidden("在讀取Twitch API時發生錯誤", f"[{r.status_code}] {apidata['message']}")

    def _build_request(self, endpoint: str, params: dict, model: T) -> Iterator[T]:
        after = True
        while after:
            r = requests.get(f"{self.BaseURL}/{endpoint}", params=params, headers=self.headers)
            r.raise_for_status()
            apidata = r.json()
            if r.ok:
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
        r = requests.get(f"{self.BaseURL}/streams", params=params, headers=self.headers)
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
        r = requests.get(f"{self.BaseURL}/users", params=params, headers=self.headers)
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
        r = requests.get(f"{self.BaseURL}/users", params=params, headers=self.headers)
        apidata = r.json()
        if apidata.get("data"):
            return TwitchUser(**apidata["data"][0])
        else:
            return None

    def get_videos(
        self, user_ids: str | list[str] = None, video_ids: str | list[str] = None, types: str | list[str] = "highlight", after: datetime = None
    ) -> list[TwitchVideo] | None:
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

        r = requests.get(f"{self.BaseURL}/videos", params=params, headers=self.headers)
        apidata = r.json()
        if apidata.get("data"):
            results = [TwitchVideo(**i) for i in apidata["data"]]
            if after:
                results = [i for i in results if i.created_at > after]
            return results
        else:
            return None

    def get_clips(self, broadcaster_id: int, started_at: datetime = None):
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

        r = requests.get(f"{self.BaseURL}/clips", params=params, headers=self.headers)
        apidata = r.json()
        if apidata.get("data"):
            if started_at:
                return [clip for clip in [TwitchClip(**i) for i in apidata["data"]] if clip.created_at > started_at]
            else:
                return [TwitchClip(**i) for i in apidata["data"]]
        else:
            return None


class YoutubeAPI:
    BaseURL = "https://www.googleapis.com/youtube/v3"

    def __init__(self):
        self.__token = sqldb.get_bot_token(APIType.Google).access_token
        self.__headers = {"x-goog-api-key": self.__token, "Accept": "application/json"}

    def get_channel_id(self, channel_handle: str) -> str | None:
        """
        Retrieves the channel ID for a given channel handle.

        Args:
            channel_handle (str): The handle of the channel.

        Returns:
            str | None: The ID of the channel if found, None otherwise.
        """
        params = {"forHandle": channel_handle, "part": "id", "maxResults": 1}
        r = requests.get(f"{self.BaseURL}/channels", params=params, headers=self.__headers)
        if r.ok:
            data = r.json()
            if data["pageInfo"]["totalResults"]:
                return data["items"][0]["id"]
            else:
                return None
        else:
            print(r.text)
            print(r.status_code)

    def get_channel(self, channel_id: str = None, handle: str = None):
        """獲取Youtube頻道資訊
        :param id: 頻道ID
        :param handle: 頻道名稱
        兩者擇一提供即可
        """
        params = {"id": channel_id, "forHandle": handle, "part": "statistics,snippet", "maxResults": 1}
        r = requests.get(f"{self.BaseURL}/channels", params=params, headers=self.__headers)
        if r.ok:
            return YoutubeChannel(**r.json().get("items")[0]) if r.json().get("items") else None
        else:
            raise APIInvokeError("youtube_get_video", f"[{r.status_code}] {r.text}")

    def get_channelsection(self, channel_id: str):
        params = {"key": self.__token, "channelId": channel_id, "part": "contentDetails"}
        r = requests.get(f"{self.BaseURL}/channelSections", params=params)
        if r.status_code == 200:
            print(r)
            print(r.json())
        else:
            print(r.text)
            print(r.status_code)

    def get_streams(self, channel_ids: list):
        print(",".join(channel_ids))
        params = {"key": self.__token, "part": "snippet", "channelId": ",".join(channel_ids), "eventType": "live", "type": "video"}
        r = requests.get(f"{self.BaseURL}/search", params=params)
        if r.ok:
            print(r)
            print(r.json())
        else:
            print(r.text)
            print(r.status_code)

    def get_stream(self, channel_id: str):
        """取得Youtube直播資訊（若無正在直播則回傳None）"""
        params = {"part": "snippet", "channelId": channel_id, "eventType": "live", "type": "video"}
        r = requests.get(f"{self.BaseURL}/search", params=params, headers=self.__headers)
        if r.ok:
            return YouTubeStream(**r.json()["items"][0]) if r.json()["items"] else None
        else:
            raise APIInvokeError("youtube_get_stream", f"[{r.status_code}] {r.text}")

    def get_video(self, video_id: str | list) -> list[YoutubeVideo]:
        params = {"part": "snippet,liveStreamingDetails", "id": video_id}
        r = requests.get(f"{self.BaseURL}/videos", params=params, headers=self.__headers)
        if r.ok:
            return [YoutubeVideo(**i) for i in r.json()["items"]] if r.json()["items"] else list()
        else:
            raise APIInvokeError("youtube_get_video", f"[{r.status_code}] {r.text}")

    def get_playlist(self, playlist_id: str | list):
        params = {"key": self.__token, "part": "snippet,contentDetails", "id": playlist_id}
        r = requests.get(f"{self.BaseURL}/playlists", params=params)
        if r.ok:
            return r.json()["items"][0] if r.json()["items"] else None
        else:
            print(r.text)
            print(r.status_code)
            return None

    def get_playlist_item(self, playlist_id: str | list):
        params = {"key": self.__token, "part": "snippet,contentDetails", "playlistId": playlist_id}
        r = requests.get(f"{self.BaseURL}/playlistItems", params=params)
        if r.ok:
            return r.json()["items"][0] if r.json()["items"] else None
        else:
            print(r.text)
            print(r.status_code)
            return None


class YoutubeRSS:
    def get_videos(self, channel_id, after: datetime = None) -> list[YoutubeRSSVideo]:
        """從RSS取得影片（由新到舊）"""
        feed = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}")
        # for entry in feed['entries']:
        #     print(entry)
        results = [YoutubeRSSVideo(**i) for i in feed["entries"]]
        if after:
            return [i for i in results if i.uplood_at > after]
        else:
            return results


class YoutubePush:
    def __init__(self):
        pass

    def add_push(self, channel_id: str, callback_url: str, secret: str = None):
        data = {
            "hub.callback": callback_url,
            "hub.topic": f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}",
            "hub.verify": "sync",
            "hub.mode": "subscribe",
            "hub.verify_token": None,
            "hub.secret": secret,
            "hub.lease_numbers": None,
        }
        r = requests.post("https://pubsubhubbub.appspot.com/subscribe", data=data)
        if r.status_code != 204:
            raise APIInvokeError(f"[{r.status_code}] youtube_push", f"[{r.status_code}] {r.text}")

    def get_push(self, channel_id: str, callback_url: str, secret: str = None):
        params = {"hub.callback": callback_url, "hub.topic": f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}", "hub.secret": secret}
        r = requests.get("https://pubsubhubbub.appspot.com/subscription-details", params=params)
        if r.ok:
            return self._parse_subscription_details(r.text)
        else:
            print(r.text)
            print(r.status_code)
            return None

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
            if time_str.strip().lower() == "n/a":
                return None
            try:
                return datetime.strptime(time_str, "%a, %d %b %Y %H:%M:%S %z").astimezone(tz=tz)
            except ValueError as e:
                log.error("時間格式錯誤: %s，原始時間字串: %s", e, time_str)
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


class GoogleCloud:
    def __init__(self):
        self.creds = self.get_creds()

    def get_creds(self):
        # If modifying these scopes, delete the file token.json.
        SCOPES = ["https://www.googleapis.com/auth/drive"]
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        creds = sqldb.get_google_credentials()
        # if os.path.exists('database/google_token.json'):
        #     creds = Credentials.from_authorized_user_file('database/google_token.json', SCOPES)

        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            token = sqldb.get_bot_token(APIType.Google, 2)
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
            token.client_id = creds.client_id
            token.client_secret = creds.client_secret
            sqldb.merge(token)

        return creds

    def list_drive_files(self):
        """Shows basic usage of the Drive v3 API.
        Prints the names and ids of the first 10 files the user has access to.
        """

        try:
            service = build("drive", "v3", credentials=self.creds)

            # Call the Drive v3 API
            results = service.files().list(
                pageSize=10, fields="nextPageToken, files(id, name)").execute()
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

    def list_file_permissions(self,fileId):
        service = build("drive", "v3", credentials=self.creds)
        results = service.permissions().list(fileId=fileId).execute()
        print(results)
        return results

    def add_file_permissions(self,fileId,emailAddress):
        service = build("drive", "v3", credentials=self.creds)
        permission_dict = {"role": "reader", "type": "user", "emailAddress": emailAddress}
        results = service.permissions().create(fileId=fileId,body=permission_dict).execute()
        print(results)
        return results

    def remove_file_permissions(self,fileId,permissionId):
        service = build("drive", "v3", credentials=self.creds)
        results = service.permissions().delete(fileId=fileId,permissionId=permissionId).execute()
        print(results)
        return results

class NotionAPI():
    def __init__(self):
        self.headers = self._get_headers()
        self.url = "https://api.notion.com/v1"

    def _get_headers(self):
        token = sqldb.get_bot_token(APIType.Notion).access_token
        return {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }

    def get_page(self,page_id:str):
        r = requests.get(f"{self.url}/pages/{page_id}",headers=self.headers)
        apidata = r.json()
        if r.ok:
            return NotionPage(**apidata)
        else:
            return apidata["message"]

    def get_page_property(self,page_id:str,property_id:str):
        r = requests.get(f"{self.url}/pages/{page_id}/properties/{property_id}",headers=self.headers)
        apidata = r.json()
        if r.status_code == 200:
            return apidata
        else:
            print(apidata["message"])

    def get_block(self,block_id:str):
        r = requests.get(f"{self.url}/blocks/{block_id}",headers=self.headers)
        apidata = r.json()
        if r.status_code == 200:
            return NotionBlock(**apidata)
        else:
            return apidata["message"]

    def get_block_children(self,block_id:str):
        r = requests.get(f"{self.url}/blocks/{block_id}/children",headers=self.headers)
        apidata = r.json()
        if r.status_code == 200:
            return NotionQueryResponse(**apidata)
        else:
            return apidata["message"]

    def search(self, title: str, page_size=100):
        """search by title"""
        data = {"query": title, "page_size": page_size}
        r = requests.post(f"{self.url}/search", json=data, headers=self.headers)
        apidata = r.json()
        if r.ok:
            try:
                return NotionQueryResponse(**apidata)
            except Exception as e:
                print(f"解析 Notion 搜尋結果時發生錯誤: {e}")
                print(f"原始數據: {apidata}")
                return None
        else:
            return apidata["message"]

    def get_database(self, database_id: str):
        """取得Notion資料庫"""
        r = requests.get(f"{self.url}/databases/{database_id}", headers=self.headers)
        apidata = r.json()
        if r.ok:
            return NotionDatabase(**apidata)
        else:
            return apidata["message"]

class RssHub():
    def __init__(self):
        self.url = "https://rsshub.app"
        self.url_local = "http://localhost:1200"

    def get_twitter(self, username: str, local=False, after: datetime | None = None):
        """取得Twitter用戶的RSS"""
        #* api不支援id查詢 故使用username查詢
        if local:
            try:
                r = requests.get(f"{self.url_local}/twitter/user/{username}")
                r.raise_for_status()
            except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError):
                r = requests.get(f"{self.url}/twitter/user/{username}")
        else:
            r = requests.get(f"{self.url}/twitter/user/{username}")

        if r.ok:
            feeds = feedparser.parse(r.text)
            results = [RssHubTwitterTweet(**feed) for feed in feeds.entries]
            results.reverse()

            if after:
                return [result for result in results if result.published_parsed > after]
            else:
                return results

        else:
            if r.status_code == 503:
                # 503可能為找不到用戶
                return
            else:
                raise APIInvokeError("rsshub_get_twitter", f"[{r.status_code}]")

class CLIInterface():
    def __init__(self):
        self.rettiwt_api_key = sqldb.get_bot_token(APIType.Rettiwt).access_token

    def get_user_timeline(self, user_id:str, after:datetime=None) -> RettiwtTweetTimeLineResponse | None:
        # shutil.which("rettiwt")
        r = subprocess.run(f'rettiwt -k "{self.rettiwt_api_key}" user timeline "{user_id}" 10', shell=True, capture_output=True, encoding="utf-8", check=False)
        r.check_returncode()
        data = json.loads(r.stdout)

        if data.get("name") == "VALIDATION_ERROR":
            return None

        results = RettiwtTweetTimeLineResponse(**data)
        if after:
            results.list = [i for i in results.list if i.createdAt > after]
        return results

    def get_user_details(self, user_id_or_name: str) -> RettiwtTweetUser | None:
        r = subprocess.run(
            f'rettiwt -k "{self.rettiwt_api_key}" user details "{user_id_or_name}"', shell=True, capture_output=True, encoding="utf-8", check=False
        )
        r.check_returncode()
        data = json.loads(r.stdout)

        if data.get("name") == "VALIDATION_ERROR":
            return None

        return RettiwtTweetUser(**data)
