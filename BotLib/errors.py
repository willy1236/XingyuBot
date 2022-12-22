class Error(Exception):
    pass
        
class Error1(Error):
    def __init__(self):
        self.code = 1
        self.message = None
        self.original = None
