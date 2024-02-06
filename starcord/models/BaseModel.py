class ListObject():
    def __init__(self, lst=None):
        self.items = lst if lst else []

    def append(self, item):
        self.items.append(item)

    def __getitem__(self, index):
        if 0 <= index < len(self.items):
            return self.items[index]
        else:
            raise IndexError("Index out of range")


    def __setitem__(self, index, value):
        self.items[index] = value

    def __delitem__(self, index):
        del self.items[index]

    def __len__(self):
        return len(self.items)

    def __repr__(self):
        return repr(self.items)
    
class BaseVideo:
    pass

class BaseUser:
    pass