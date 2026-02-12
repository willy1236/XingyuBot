import requests

from ..fileDatabase import Jsondb


class JsonStorageAPI:
    """https://www.jsonstorage.net/"""
    def __init__(self):
        self.url = "https://api.jsonstorage.net/v1/json"
        tokens = Jsondb.get_token("jsonstorage_api")
        self.userId = tokens[0]
        self.itemId = tokens[1]
        self.token = tokens[2]
        self.params = {
            "apiKey":self.token
        }

    def get(self):
        r = requests.get(f"{self.url}/{self.userId}/{self.itemId}", params=self.params)
        if r.status_code == 200:
            return r.json()
        else:
            print(r.status_code, r.reason)
            return None

    def post(self,data):
        """create a new json storage"""
        r = requests.post(f"{self.url}", json=data, params=self.params)
        print(r.json())

    def put(self, data):
        """update current json data"""
        r = requests.put(f"{self.url}/{self.userId}/{self.itemId}", json=data, params=self.params)
        if r.status_code == 200:
            print(r.json())
        else:
            print(r.status_code, r.reason)

    def patch(self,data):
        r = requests.patch(f"{self.url}/{self.userId}/{self.itemId}", json=data, params=self.params)
        print(r.json())

    def append_data(self,data):
        apidata = self.get()
        if apidata or apidata == []:
            apidata.append(data)
            print(apidata)
            self.put(apidata)
        else:
            print("No apidata found.")

    def remove_first_data(self, data):
        pass
