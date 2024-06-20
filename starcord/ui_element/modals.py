import discord
import genshin

from ..database import sqldb

class HoyolabCookiesModal(discord.ui.Modal):
    def __init__(self) -> None:
        super().__init__(title="Hoyolab Cookies")
        self.add_item(discord.ui.InputText(label="ltuid_v2"))
        self.add_item(discord.ui.InputText(label="ltmid_v2"))
        self.add_item(discord.ui.InputText(label="ltoken_v2"))

    async def callback(self, interaction: discord.Interaction):
        cookies = {
            "ltuid_v2": self.children[0].value,
            "ltmid_v2": self.children[1].value,
            "ltoken_v2": self.children[2].value
        }
        try:
            client = genshin.Client(cookies)
            user = await client.get_hoyolab_user()
            sqldb.set_hoyo_cookies(interaction.user.id, cookies)
            await interaction.response.send_message(f"cookies設定完成，登入身分：{user.nickname}({user.hoyolab_id})", ephemeral=True)
        except genshin.errors.InvalidCookies:
            await interaction.response.send_message(f"cookies無效：請確認是否輸入正確的cookies", ephemeral=True)