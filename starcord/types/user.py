from enum import Enum

pet_tl = {
    "en":{
        "shark": "shark",
        "dog": "dog",
        "cat": "cat",
        "fox": "fox",
        "wolf": "wolf"
    },
    "zh-tw":{
        "shark": "鯊魚",
        "dog": "狗",
        "cat": "貓",
        "fox": "狐狸",
        "wolf": "狼"

    }
}

class PetType(Enum):
    SHARK = 'shark'
    DOG = "dog"
    CAT = "cat"
    FOX = "fox"
    WOLF = "wolf"

    # def __init__(self,value,*args):
    #     print(args,value)
        # self.lcode = lcode
        # self._name = name
        # self._value = value
        # self._value_ = value

    # @property
    # def name(self):
    #     if self.lcode == "en":
    #         return self.name
    #     else:
    #         return pet_tl[self.lcode][self._value]

    def display(self,lcode='en'):
        return pet_tl[lcode][self.value]
    
    # def __new__(cls, value, extra):
    #     obj = str.__new__(cls, [value])
    #     obj._value_ = value
    #     obj.extra = extra
    #     return obj

class BusyTime(Enum):
    早上 = 1
    下午 = 2
    晚上 = 3