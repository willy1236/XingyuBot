from . import model
from . import interface

from .database import *
from .file_database import *
from .basic import *



Jsondb = JsonDatabase()
settings = Jsondb.get('SQL_connection')
if settings:
    sqldb = MySQLDatabase(**settings)