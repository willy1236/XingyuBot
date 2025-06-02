import discord

from starlib import BotEmbed


class RuleMessageModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="規則訊息")
        self.add_item(discord.ui.InputText(label="規則標題", style=discord.InputTextStyle.short))
        self.add_item(discord.ui.InputText(label="規則內容", style=discord.InputTextStyle.long))

    async def callback(self, interaction: discord.Interaction):
        await interaction.respond("完成填寫規則訊息", ephemeral=True)
