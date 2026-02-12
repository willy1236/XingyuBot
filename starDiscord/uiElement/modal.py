import discord

from starlib import BotEmbed, sqldb
from starlib.models.postgresql import ExternalAccount
from starlib.types import PlatformType


class RuleMessageModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="規則訊息")
        self.add_item(discord.ui.InputText(label="規則標題", style=discord.InputTextStyle.short))
        self.add_item(discord.ui.InputText(label="規則內容", style=discord.InputTextStyle.long))

    async def callback(self, interaction: discord.Interaction):
        await interaction.respond("完成填寫規則訊息", ephemeral=True)

class LinkAccountModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="綁定現有帳號")
        self.add_item(discord.ui.InputText(label="舊帳號的 Discord ID", placeholder="例如: 123456789..."))
        self.add_item(discord.ui.InputText(label="驗證碼", placeholder="請從舊帳號使用 /get_link_code 取得"))

    async def callback(self, interaction: discord.Interaction):
        old_dc_id = self.children[0].value
        v_code = self.children[1].value

        old_user = interaction.client.get_user(int(old_dc_id))
        if not old_user:
            return await interaction.response.send_message("❌ 找不到該舊帳號的 Discord 用戶，請確認 ID 是否正確。", ephemeral=True)

        active_link_code = sqldb.get_active_link_code(old_dc_id)
        if not active_link_code or active_link_code.code != v_code:
            return await interaction.response.send_message("❌ 驗證碼錯誤或已過期，請重新嘗試。", ephemeral=True)

        # 綁定帳號
        new_link = ExternalAccount(user_id=active_link_code.user_id, platform=PlatformType.Discord, external_id=str(interaction.user.id), display_name=interaction.user.display_name)
        sqldb.session.add(new_link)
        sqldb.session.delete(active_link_code)  # 使用完畢後刪除驗證碼
        sqldb.commit()

        await interaction.response.send_message("✅ 帳號綁定成功！您現在可以使用現有進度了。", ephemeral=True)
