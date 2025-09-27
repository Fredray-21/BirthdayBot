from discord import Embed, ButtonStyle, Interaction
from discord.ui import View, Button
import discord
import re
from datetime import datetime

ITEMS_PER_PAGE = 15

def escape_markdown(text: str) -> str:
    # Échapper les caractères Markdown communs
    return re.sub(r'([*_~`>])', r'\\\1', text)

class BirthdayPaginator(View):
    def __init__(self, ctx, birthdays):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.birthdays = list(birthdays.items())
        self.current_page = 0
        self.max_page = (len(self.birthdays) - 1) // ITEMS_PER_PAGE

        # Initialiser les boutons désactivés si nécessaire
        if self.max_page == 0:
            self.previous_button.disabled = True
            self.next_button.disabled = True
        else:
            self.previous_button.disabled = True  # page 0 = début
            self.next_button.disabled = False     # il y a une page suivante
            
            
    def get_embed(self):
        start = self.current_page * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        entries = self.birthdays[start:end]

        embed = Embed(
            title="🎂 Anniversaires enregistrés",
            description=f"Page {self.current_page+1}/{self.max_page+1}",
            color=0xFFC0CB
        )

        for member_id, birthday_date in entries:
            member = self.ctx.guild.get_member(int(member_id))
            
            # Fallback si membre absent
            if member:
                member_name = f"{member.display_name} ({member.name})"
                safe_name = escape_markdown(member_name)
            else:
                safe_name = f"({member_id})"

            # Formater la date
            dt = datetime.strptime(birthday_date, "%Y-%m-%d")
            formatted_date = dt.strftime("%d/%m/%Y")
            
            embed.add_field(
                name=safe_name,
                value=formatted_date,
                inline=False
            )

        return embed


    @discord.ui.button(label="◀", style=ButtonStyle.secondary)
    async def previous_button(self, interaction: Interaction, button: Button):
        if self.current_page > 0:
            self.current_page -= 1
        # mettre à jour disabled
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = False
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="▶", style=ButtonStyle.secondary)
    async def next_button(self, interaction: Interaction, button: Button):
        if self.current_page < self.max_page:
            self.current_page += 1
        # mettre à jour disabled
        self.next_button.disabled = self.current_page == self.max_page
        self.previous_button.disabled = False
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="❌", style=ButtonStyle.danger)
    async def close_button(self, interaction: Interaction, button: Button):
        # Supprime le message et stoppe la view
        await interaction.message.delete()
        self.stop()