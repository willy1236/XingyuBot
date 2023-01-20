from . import model
from . import interface

from .database import *
from .file_database import *
from .basic import *



Jsondb = JsonDatabase()
settings = Jsondb.jdata.get('SQLsettings')
if settings:
    sqldb = MySQLDatabase(**settings)