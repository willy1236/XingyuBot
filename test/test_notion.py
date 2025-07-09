from starlib import NotionAPI

api = NotionAPI()
# result = api.search("")

# if result:
#     for i, item in enumerate(result.results):
#         print(item.id)
#         if hasattr(item, "embed"):
#             embed = item.embed()
#             print(f"  標題: {embed.title}")
#             print(f"  URL: {embed.url}")
# else:
#     print("搜尋結果為空或發生錯誤")

result = api.get_page("")
# result = api.get_block("")
# result = api.get_block_children("")
# for i, item in enumerate(result.results):
#     print(i, item.get_plain_text())
print(result)
