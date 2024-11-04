import threading
from typing import TypeVar

T = TypeVar("T")

class BaseThread(threading.Thread):
    """
    A base class for creating custom threads.
    """
    def __init__(self, name):
        super().__init__(name=name)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

class ListObject(list[T]):
    """
    A class representing a list object with additional functionality.

    Attributes:
        items (list): The list of items stored in the object.
    """

    def __init__(self, lst:list[T]=None):
        self.items:list[T] = lst if lst else []

    def append(self, item:T):
        self.items.append(item)

    def __getitem__(self, index:int):
        if 0 <= index < len(self.items):
            return self.items[index]
        else:
            raise IndexError("Index out of range")

    def __setitem__(self, index:int, value:T):
        self.items[index] = value

    def __delitem__(self, index:int):
        del self.items[index]

    def __len__(self):
        return len(self.items)

    def __repr__(self):
        return repr(self.items)
    
    def __iter__(self):
        return iter(self.items)