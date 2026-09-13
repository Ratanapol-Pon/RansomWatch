import asyncio
import io
import logging

import discord
from discord import app_commands
from discord.ext import commands

from packages.bot.brief import build_brief
from packages.bot.chart import render_stats_chart
from packages.bot.chatbot import run_chat
from packages.bot.formatting import chunk_text, incident_list_text
from packages.bot.llm import build_llm
from packages.bot.permissions import ADMIN_ONLY_MESSAGE, is_admin
from packages.bot.queries import Queries
from packages.bot.stats import count_by_day, count_by_group, in_period, period_days
from packages.shared.config import Settings, get_settings
from packages.shared.db import get_session

logger = logging.getLogger(__name__)

PERIOD_CHOICES = [app_commands.Choice(name=p, value=p) for p in ("7d", "30d", "90d")]


def _admin_check(admin_role_id: int | None):
    async def predicate(interaction: discord.Interaction) -> bool:
        role_ids = [r.id for r in getattr(interaction.user, "roles", [])]
        if is_admin(role_ids, admin_role_id):
            return True
        await interaction.response.send_message(ADMIN_ONLY_MESSAGE, ephemeral=True)
        return False

    return app_commands.check(predicate)


class RansomWatchBot(commands.Bot):
    def __init__(self, settings: Settings):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.settings = settings
        self.admin_role_id = (
            int(settings.discord_admin_role_id) if settings.discord_admin_role_id else None
        )
        self.ask_channel_id = (
            int(settings.discord_ask_channel_id) if settings.discord_ask_channel_id else None
        )
        self.llm = build_llm(settings)

    async def setup_hook(self) -> None:
        self._register_commands()
        if self.settings.discord_guild_id:
            guild = discord.Object(id=int(self.settings.discord_guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        logger.info("slash commands synced")

    async def on_ready(self) -> None:
        logger.info("logged in as %s", self.user)

    def _run_queries(self, fn):
        async def wrapper(*args):
            def work():
                with get_session() as session:
                    return fn(Queries(session), *args)

            return await asyncio.to_thread(work)

        return wrapper

    def _register_commands(self) -> None:
        tree = self.tree
        run = self._run_queries

        @tree.command(name="latest", description="Last n ransomware victims in Thailand")
        @app_commands.describe(n="number of incidents (default 5, max 25)")
        async def latest(interaction: discord.Interaction, n: int = 5) -> None:
            await interaction.response.defer()
            incidents = await run(lambda q: q.latest(n))()
            text = incident_list_text(incidents, "No incidents recorded in the database yet.")
            await _reply(
                interaction, f"**Latest {len(incidents)} incident(s) — Thailand**\n\n{text}"
            )

        @tree.command(name="victim", description="Search incidents by company name")
        @app_commands.describe(name="company name to search")
        async def victim(interaction: discord.Interaction, name: str) -> None:
            await interaction.response.defer()
            incidents = await run(lambda q: q.search_victim(name))()
            text = incident_list_text(incidents, f"No records found for '{name}' in the database.")
            await _reply(interaction, text)

        @tree.command(name="group", description="Ransomware group profile + Thai victims")
        @app_commands.describe(name="group name")
        async def group(interaction: discord.Interaction, name: str) -> None:
            await interaction.response.defer()
            canonical, victims = await run(lambda q: q.group_profile(name))()
            if not victims:
                await _reply(interaction, f"No records found for group '{name}'.")
                return
            text = incident_list_text(victims[:10], "")
            await _reply(
                interaction,
                f"**Group: {canonical}** — {len(victims)} Thai victim(s)\n\n{text}",
            )

        @tree.command(name="stats", description="Summary chart of Thai victims (7d/30d/90d)")
        @app_commands.describe(period="lookback window")
        @app_commands.choices(period=PERIOD_CHOICES)
        async def stats(interaction: discord.Interaction, period: str = "30d") -> None:
            await interaction.response.defer()

            def work(q: Queries):
                days = period_days(period)
                scoped = in_period(q.all_incidents(), days)
                png = render_stats_chart(count_by_day(scoped, days), count_by_group(scoped), period)
                return len(scoped), png

            total, png = await run(work)()
            file = discord.File(io.BytesIO(png), filename=f"stats_{period}.png")
            await interaction.followup.send(
                f"**{total} victim(s) in the last {period} — Thailand**", file=file
            )

        @tree.command(name="brief", description="Customer-meeting-ready brief (≤5 sourced bullets)")
        @app_commands.describe(
            topic="sector or group (e.g. manufacturing, lockbit); empty = Thailand overall",
            period="lookback window",
        )
        @app_commands.choices(period=PERIOD_CHOICES)
        async def brief(
            interaction: discord.Interaction, topic: str = "", period: str = "90d"
        ) -> None:
            await interaction.response.defer()
            bullets = await run(lambda q: build_brief(q.all_incidents(), topic, period))()
            label = topic or "Thailand overall"
            text = "\n".join(f"• {b}" for b in bullets)
            await _reply(interaction, f"**Brief — {label} — last {period}**\n\n{text}")

        @tree.command(name="watch", description="Add a company to the watchlist (admin)")
        @app_commands.describe(company="company name to watch")
        @_admin_check(self.admin_role_id)
        async def watch(interaction: discord.Interaction, company: str) -> None:
            await interaction.response.defer(ephemeral=True)
            entry = await run(lambda q: q.add_watch(company))()
            if entry is None:
                await _reply(interaction, f"'{company}' is already on the watchlist.")
            else:
                await _reply(interaction, f"✅ Added **{entry.name}** to the watchlist.")

        @tree.command(name="unwatch", description="Remove a company from the watchlist (admin)")
        @app_commands.describe(company="company name to remove")
        @_admin_check(self.admin_role_id)
        async def unwatch(interaction: discord.Interaction, company: str) -> None:
            await interaction.response.defer(ephemeral=True)
            try:
                removed = await run(lambda q: q.remove_watch(company))()
            except ValueError as exc:
                await _reply(interaction, str(exc))
                return
            if removed is None:
                await _reply(interaction, f"'{company}' is not on the watchlist.")
            else:
                await _reply(interaction, f"🗑️ Removed **{removed}** from the watchlist.")

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not self._is_ask_channel(message):
            return
        question = message.content.strip()
        if not question:
            return

        async with message.channel.typing():
            try:
                answer = await asyncio.to_thread(self._answer, question)
            except Exception:
                logger.exception("chatbot failed for question: %s", question)
                answer = "Something went wrong while looking that up. Please try again."
        for chunk in chunk_text(answer):
            await message.reply(chunk, mention_author=False)

    def _is_ask_channel(self, message: discord.Message) -> bool:
        if self.ask_channel_id:
            return message.channel.id == self.ask_channel_id
        return getattr(message.channel, "name", "") == "ask-ransomwatch"

    def _answer(self, question: str) -> str:
        with get_session() as session:
            return run_chat(question, self.llm, Queries(session))


async def _reply(interaction: discord.Interaction, text: str) -> None:
    chunks = chunk_text(text)
    await interaction.followup.send(chunks[0])
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.discord_bot_token:
        raise RuntimeError("DISCORD_BOT_TOKEN is not set")
    bot = RansomWatchBot(settings)
    bot.run(settings.discord_bot_token, reconnect=True, log_handler=None)


if __name__ == "__main__":
    main()
