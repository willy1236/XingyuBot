# google_oauth.py
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from starlib.database import PlatformType

from .oauth_lib import OAuth2Base


class GoogleOAuth(OAuth2Base):
    # FIXME: 重新補齊原本的功能
    auth_url = "https://accounts.google.com/o/oauth2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    api_url = "https://www.googleapis.com/oauth2/v1"
    platform_type = PlatformType.Google

    def to_google_creds(self, token):
        return Credentials(
            token=token["access_token"],
            refresh_token=token.get("refresh_token"),
            expiry=token["expires_at"].replace(tzinfo=None),
        )

    def build_service(self, token, service="people", version="v1"):
        creds = self.to_google_creds(token)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build(service, version, credentials=creds)

    async def get_me(self, token):
        return await self.api_get(token, "/userinfo")

# class GoogleOauthOld(OAuth2Base):
#     auth_url = "https://accounts.google.com/o/oauth2/auth"
#     token_url = "https://oauth2.googleapis.com/token"
#     api_url = "https://www.googleapis.com/oauth2/v1"
#     platform_type = PlatformType.Google

#     def __init__(self, client_id=None, client_secret=None, redirect_uri="https://localhost:14000/oauth/google", scopes=None, user_id=None):
#         if not client_id or not client_secret:
#             token = sqldb.get_bot_token(PlatformType.Google, 3)
#             client_id = token.client_id
#             client_secret = token.client_secret

#         super().__init__(client_id, client_secret, redirect_uri, scopes)
#         self._user_id = user_id
#         self._creds = None

#     @property
#     def creds(self) -> Credentials:
#         if self._creds is None:
#             self.set_creds()
#         elif self._creds.expired and self._creds.refresh_token:
#             self._creds.refresh(Request())
#             self.access_token = self._creds.token
#             self.refresh_token = self._creds.refresh_token
#             self.expires_at = self._creds.expiry.replace(tzinfo=timezone(timedelta(hours=0))).astimezone(tz)
#             self.save_token(self.user_id)
#         return self._creds  # type: ignore

#     @property
#     def user_id(self):
#         if self._user_id is None:
#             try:
#                 apidata = self.get_me()
#                 self._user_id = apidata["id"]
#             except KeyError:
#                 print(apidata)
#                 raise
#         return self._user_id

#     def set_creds(self, creds=None):
#         """
#         設定 Google OAuth2 的憑證。\\
#         會依user_id、傳入的 creds、access_token 的順序來取得憑證。\\
#         如果都沒有且在debug_mode下，則會從 Google OAuth2 隱式授權中取得 token。
#         """
#         if self._user_id:
#             self.load_token_from_db(self._user_id)
#             self._creds = Credentials(token=self.access_token, refresh_token=self.refresh_token, expiry=self.expires_at.replace(tzinfo=None))
#         elif creds:
#             self._creds = creds
#         elif self.access_token:
#             self._creds = Credentials(token=self.access_token, refresh_token=self.refresh_token, expiry=self.expires_at.replace(tzinfo=None))

#         if debug_mode and (not self._creds or not self._creds.valid):
#             if self._creds and self._creds.expired and self._creds.refresh_token:
#                 self._creds.refresh(Request())
#             else:
#                 # flow = InstalledAppFlow.from_client_secrets_file(
#                 #     'database/google_client_credentials.json', self.scopes)
#                 client_config = sqldb.get_google_client_config(3)
#                 flow = InstalledAppFlow.from_client_config(client_config, self.scopes)
#                 self._creds = flow.run_local_server()

#                 self.access_token = self._creds.token
#                 self.refresh_token = self._creds.refresh_token
#                 self.expires_at = self._creds.expiry.replace(tzinfo=timezone(timedelta(hours=0))).astimezone(tz)
#                 self.save_token(self.user_id)

#     def get_me(self):
#         return self.get(f"{self.api_url}/userinfo")

#     def get_user(self, user_id="me"):
#         service = build("people", "v1", credentials=self.creds)
#         results = service.people().get(resourceName=f"people/{user_id}", personFields="names,emailAddresses").execute()
#         return results

#     def get_mine_channel(self):
#         service = build("youtube", "v3", credentials=self.creds)
#         results = service.channels().list(mine=True, part="snippet").execute()
#         return results

#     def list_playlists(self):
#         service = build("youtube", "v3", credentials=self.creds)
#         results = service.playlists().list(part="snippet", mine=True).execute()
#         return results

#     def get_playlist_item(self, playlist_id, nextPageToken=None):
#         service = build("youtube", "v3", credentials=self.creds)
#         if isinstance(nextPageToken, str):
#             results = service.playlistItems().list(part="snippet", playlistId=playlist_id, pageToken=nextPageToken, maxResults=50).execute()
#         else:
#             results = service.playlistItems().list(part="snippet", playlistId=playlist_id, maxResults=50).execute()
#         return results

#     def add_song_to_playlist(self, playlist_id, video_id):
#         service = build("youtube", "v3", credentials=self.creds)
#         request = service.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}})
#         return request.execute()

#     def remove_song_from_playlist(self, video_in_playlist_id):
#         service = build("youtube", "v3", credentials=self.creds)
#         request = service.playlistItems().delete(id=video_in_playlist_id)
#         return request.execute()
