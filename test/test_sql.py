from datetime import datetime

from sqlalchemy import and_, delete, desc, func, or_
from sqlmodel import select

from starlib import NotifyCommunityType, sqldb, tz
from starlib.models.postgresql import Post, ReactionRoleMessage, User

user = User(age=20)
user.id = 3
user = sqldb.merge(user)
print(user)

# # 建立使用者 - 不指定 id，讓資料庫自動生成
# new_user = User(name="Alice", age=30)
# print(new_user)
# session.add(new_user)
# session.commit()
# print(new_user.id)

# 建立貼文
# new_post = Post(title="My First Post", content="Hello, world!", created_at=datetime.now(tz), user_id=1)
# print(new_post)
# sqldb.session.add(new_post)
# sqldb.session.commit()

# stmt = select(User).where(User.name == "Alice")
# user = sqldb.session.exec(stmt).one_or_none()[0]
# print(user)
# user.name = "Alice"
# new_user = sqldb.session.merge(user)
# sqldb.session.commit()
# print(new_user)


# # 查詢資料
# user = session.query(User).filter_by(id=new_user.id).first()
# print(f"User: {user.name}, ID: {user.id}")
# print(f"Posts: {user.posts}")  # 會輸出 Alice 的所有貼文

# user = sqldb.get_dcuser_test_session(419131103836635136)
# print(user.discord_id)
