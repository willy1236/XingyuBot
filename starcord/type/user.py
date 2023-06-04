from enum import Enum

pet_tl = {
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

    def __init__(self, value,lcode='en'):
        self.lcode = lcode
        self._value = value
        
    @property
    def value(self):
        if self.lcode == "en":
            return self._value
        else:
            return pet_tl[self.lcode][self._value]