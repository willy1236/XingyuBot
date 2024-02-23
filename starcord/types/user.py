from enum import Enum,IntEnum

pet_tl = {
    "en":{
        "1": "shark",
        "2": "dog",
        "3": "cat",
        "4": "fox",
        "5": "wolf"
    },
    "zh-tw":{
        "1": "鯊魚",
        "2": "狗",
        "3": "貓",
        "4": "狐狸",
        "5": "狼"

    }
}

class PetType(IntEnum):
    SHARK = 1
    DOG = 2
    CAT = 3
    FOX = 4
    WOLF = 5

    def __str__(self):
        return self.text()

    def text(self,lcode='en'):
        return pet_tl[lcode][str(self.value)]

class BusyTime(Enum):
    早上 = 1
    下午 = 2
    晚上 = 3

class Coins(Enum):
    POINT = "point"
    RCOIN = "rcoin"
    SCOIN = "scoin"

class Position(Enum):
    PRESIDENT= "president"
    EXECUTIVE_PRESIDENT  = "executive_president"
    LEGISLATIVE_PRESIDENT  = "legislative_president"
    JUDICIARY_PRESIDENT = "judiciary_president"