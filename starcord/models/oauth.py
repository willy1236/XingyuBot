class UserConnection:
    """Connection Data from Discord Oauth API."""
    
    def __init__(self,dct:dict):
        self.id = dct['id']
        self.name = dct['name']
        self.type = dct['type']
        self.friend_sync = dct['friend_sync']
        self.metadata_visibility = dct['metadata_visibility']
        self.show_activity = dct['show_activity']
        self.two_way_link = dct['two_way_link']
        self.verified = dct['verified']
        self.visibility = dct['visibility']