from datetime import datetime

from sqlalchemy import select, and_, delete, desc, func, or_

from starlib.database import sqldb
from starlib.models.mysql import ReactionRoleMessage, Timetest
from starlib import tz


sqldb.alsession.merge(Timetest(id=1, time=datetime.now()))
sqldb.alsession.commit()

res = sqldb.alsession.query(Timetest).filter(Timetest.id == 1).one()
print(res.time.tzinfo)



