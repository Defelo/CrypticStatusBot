import datetime
import json
import os
import re
import time
import sentry_sdk
from typing import Optional, List, Set

from discord import Client, Message, TextChannel, Embed, Color
from discord.ext import tasks
from discord.ext.tasks import Loop
from sentry_sdk.integrations.aiohttp import AioHttpIntegration

from cryptic_client import CrypticClient
from server import Server

VERSION = "1.2"

sentry_dsn = os.environ.get("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        attach_stacktrace=True,
        shutdown_timeout=5,
        integrations=[AioHttpIntegration()],
        release=f"crypticstatusbot@{VERSION}",
    )

RESULT = [":x: Down", ":white_check_mark: Running"]
CHANNEL_CHAR = ["✘", "✔"]
SPACE = "\u2009" * 2
DOT = "\u00b7"

config: dict = json.load(open("config.json"))
servers: List[Server] = [Server.deserialize(server) for server in config["servers"]]


def validate_config():
    occupied_channels: Set[int] = set()
    for server in servers:
        assert server.channel_id not in occupied_channels, "channel is already occupied"
        occupied_channels.add(server.channel_id)


def space_channel_name(name: str) -> str:
    return name.replace(" ", SPACE)


async def fetch_status_message(channel: TextChannel) -> Optional[Message]:
    out = None
    async for message in channel.history(limit=None):
        if out is None and message.author == bot.user:
            out = message
        else:
            await message.delete()
    return out


validate_config()

bot: Client = Client()


async def microservice_status(server: Server, ms_running: bool, ms: str):
    if ms in server.ms_down:
        since, message_id = server.ms_down[ms]
        time_passed: float = time.time() - since
        channel: TextChannel = bot.get_channel(server.channel_id)
        if ms_running:
            server.ms_down.pop(ms)
            message: Optional[Message] = await channel.fetch_message(message_id)
            if message is not None:
                await message.delete()
        elif time_passed > 120 and message_id is None:
            message = await channel.send(
                f":warning: The {[ms + ' microservice', 'java server'][ms == 'server']} seems to be down!"
            )
            server.ms_down[ms] = since, message.id
    elif not ms_running:
        server.ms_down[ms] = time.time(), None


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    try:
        main_loop.start()
    except RuntimeError:
        main_loop.restart()


main_loop: Loop


# noinspection PyCallingNonCallable
@tasks.loop(seconds=config["refresh_interval"])
async def main_loop():
    for server in servers:
        # print(server)
        embed: Embed = Embed(title=f"**{server.title} - Microservice Status**", description=f"Server: {server.socket}")
        if server.frontend is not None:
            embed.description += f"\nFrontend: {server.frontend}"

        channel: TextChannel = bot.get_channel(server.channel_id)
        if channel is None:
            continue

        client: CrypticClient = CrypticClient(server)

        server_running: bool = client.check_java_server()
        embed.add_field(name="**Java Server**", value=RESULT[server_running], inline=False)
        await microservice_status(server, server_running, "server")

        all_up: bool = server_running

        for expected, microservices in server.microservices.items():
            for ms in microservices:
                ms_running: bool = server_running and client.check_microservice(ms, expected)
                embed.add_field(name=f"**cryptic-{ms}**", value=RESULT[ms_running], inline=False)
                all_up: bool = all_up and ms_running

                if server_running:
                    await microservice_status(server, ms_running, "cryptic-" + ms)

        online_count: Optional[int] = None
        if server_running:
            online_count: Optional[int] = client.request({"action": "info"}).get("online")
            if online_count is not None:
                embed.description += f"\nOnline Players: {online_count - 1}"

        client.close()

        embed.colour = [Color(0xFF0000), Color(0xFFFF00), Color(0x008800)][server_running + all_up]
        embed.set_footer(text=f"v{VERSION} - Bot by @Defelo#2022")
        embed.timestamp = datetime.datetime.utcnow()

        status_message: Optional[Message] = await fetch_status_message(channel)
        if status_message is None:
            await channel.send(embed=embed)
        else:
            await status_message.edit(content="", embed=embed)

        old_channel_name: str = re.match(r"^.*?([a-z0-9]*)$", channel.name).group(1)
        up_indicator: str = CHANNEL_CHAR[all_up]
        new_channel_name: str = f"{up_indicator} {old_channel_name}"
        new_channel_topic: str = f"Status of {server.title}"
        if server_running and online_count is not None:
            new_channel_topic += f" {DOT} Online Players: {online_count - 1}"

        await channel.edit(name=space_channel_name(new_channel_name), topic=new_channel_topic)


@bot.event
async def on_error(*_, **__):
    if sentry_dsn:
        sentry_sdk.capture_exception()
    else:
        raise


bot.run(os.environ["TOKEN"])
