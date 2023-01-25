'''Discord機器人用lib庫
'''

#from . import model
from . import interface
from .database import *

#from .database import *
#from .file_database import *
from .basic import *
from .funtions import *



Jsondb = JsonDatabase()
settings = Jsondb.jdata.get('SQLsettings')
SQL_connection = Jsondb.jdata.get('SQL_connection')

if SQL_connection and settings:
    sqldb = MySQLDatabase(**settings)
else:
    sqldb = None