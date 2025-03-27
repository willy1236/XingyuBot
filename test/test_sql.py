from datetime import datetime

from sqlalchemy import select, and_, delete, desc, func, or_

from starlib.database import sqldb
from starlib.models.mysql import ReactionRoleMessage, User, Post
from starlib import tz

session = sqldb.alsession

# 建立使用者 - 不指定 id，讓資料庫自動生成
# new_user = User(name="Alice")
# print(new_user)
# session.add(new_user)
# session.commit()
# print(new_user.id)


# # 建立貼文
# new_post = Post(
#     title="My First Post", 
#     content="Hello, world!", 
#     created_at=datetime.now(tz), 
#     user_id=new_user.id
# )
# print(new_post)
# session.add(new_post)
# session.commit()

# 查詢資料
user = session.query(User).filter_by(name="Alice").first()
print(f"User: {user.name}, ID: {user.id}")
print(f"Posts: {user.posts}")  # 會輸出 Alice 的所有貼文