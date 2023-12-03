class ListObject():
    def __init__(self):
        self.items = []

    def append(self, item):
        self.items.append(item)

    def __getitem__(self, index):
        return self.items[index]

    def __setitem__(self, index, value):
        self.items[index] = value

    def __delitem__(self, index):
        del self.items[index]

    def __len__(self):
        return len(self.items)

    def __repr__(self):
        return repr(self.items)