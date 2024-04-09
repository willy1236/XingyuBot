# from pymongo.mongo_client import MongoClient
# from pymongo.server_api import ServerApi


class MongoDB:
    """The client used for MongoDB"""
    def __init__(self,connection_url):
        """
        use MongoDB.client for any action
        :param connection_url: start with "mongodb+srv://"
        """
        self.url = connection_url
        self.client = MongoClient(self.url, server_api=ServerApi('1'))

    def get_apidata(self):
        db = self.client['star_database']
        collect = db['api_data']
        dbdata = collect.find()
        for post in dbdata:
            print(post)
            #collect.delete_one(post)
        return dbdata

if __name__ == '__main__':
    username = ""
    password = ""
    url = f""
    # Create a new client and connect to the server
    client = MongoClient(url, server_api=ServerApi('1'))
    # Send a ping to confirm a successful connection
    try:
        client.admin.command('ping')
        print("Pinged your deployment. You successfully connected to MongoDB!")
        db = client['star_database']
        collect = db['api_data']

        for post in collect.find():
            print(post)
            #collect.delete_one(post)
    except Exception as e:
        print(e)