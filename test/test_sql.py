from datetime import datetime
from starlib.database import sqldb
from starlib.models.mysql import ReactionRoleMessage, Timetest
from starlib import tz

# sqldb.session.merge(Timetest(id=1, time=datetime.now(tz)))
res = sqldb.session.query(Timetest).one()

print(res.time.tzinfo)



