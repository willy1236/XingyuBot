from starlib.fileDatabase import Jsondb

from ..base import APICaller


class JsonStorageAPI(APICaller):
    """https://www.jsonstorage.net/"""

    base_url = "https://api.jsonstorage.net/v1/json"

    def __init__(self):
        super().__init__()
        tokens = Jsondb.get_token("jsonstorage_api")
        self.userId = tokens[0]
        self.itemId = tokens[1]
        self.token = tokens[2]
        self.params = {"apiKey": self.token}

    def get(self):
        r = super().get(f"{self.userId}/{self.itemId}", params=self.params)
        return r.json()

    def post(self,data):
        """create a new json storage"""
        r = super().post("", data=data, params=self.params)
        print(r.json())

    def put(self, data):
        """update current json data"""
        r = super().put(f"{self.userId}/{self.itemId}", data=data, params=self.params)
        print(r.json())

    def patch(self,data):
        r = super().patch(f"{self.userId}/{self.itemId}", data=data, params=self.params)
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
