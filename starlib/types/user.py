from enum import Enum, IntEnum

pet_tl = {"en": {"1": "shark", "2": "dog", "3": "cat", "4": "fox", "5": "wolf"}, "zh-tw": {"1": "鯊魚", "2": "狗", "3": "貓", "4": "狐狸", "5": "狼"}}


class PetType(IntEnum):
    SHARK = 1
    DOG = 2
    CAT = 3
    FOX = 4
    WOLF = 5

    def __str__(self):
        return self.text()

    def text(self, lcode="en"):
        return pet_tl[lcode][str(self.value)]


class Coins(IntEnum):
    Point = 1
    Stardust = 2
    Rcoin = 3


class Position(IntEnum):
    PRESIDENT = 1
    EXECUTIVE_PRESIDENT = 2
    LEGISLATIVE_PRESIDENT = 3
    JUDICIARY_PRESIDENT = 4


class WarningType(IntEnum):
    Warning = 1
    Timeout = 2
    Kick = 3
    Ban = 4
