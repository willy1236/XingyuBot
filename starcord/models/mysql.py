from datetime import date
from typing import TYPE_CHECKING
class Party:
    __solts__ = ['id', 'name', 'role_id', 'creator_id', 'created_at', "member_count"]
    
    if TYPE_CHECKING:
        id: int
        name: str
        role_id: int
        creator_id: int
        created_at: date
        member_count: int | None

    def __init__(self, dct:dict):
        self.id = dct.get('party_id')
        self.name = dct.get('party_name')
        self.role_id = dct.get('role_id')
        self.creator_id = dct.get('creator_id')
        self.created_at = dct.get('created_at')
        self.member_count = dct.get('member_count')

    def __str__(self):
        return f'Party(id={self.id})'

    def __repr__(self):
        return self.__str__()
    
    def to_dict(self):
        return {
            'party_id': self.id,
            'party_name': self.name,
            'role_id': self.role_id,
            'creator_id': self.creator_id,
            'created_at': self.created_at,
            "member_count": self.member_count
        }