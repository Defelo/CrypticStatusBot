import datetime
import json
import os
import re
import time
from typing import Optional, List, Set

from discord import Client, Message, TextChannel, Embed, Color
from discord.ext import tasks

from cryptic_client import CrypticClient
from server import Server

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


class Bot(Client):
    @staticmethod
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

    async def on_ready(self):
        print(f"Logged in as {self.user}")

        self.main_loop.cancel()

        self.main_loop.start()

    # noinspection PyCallingNonCallable
    @tasks.loop(seconds=config["refresh_interval"])
    async def main_loop(self):
        for server in servers:
            # print(server)
            embed: Embed = Embed(
                title=f"**{server.title} - Microservice Status**", description=f"Server: {server.socket}"
            )
            if server.frontend is not None:
                embed.description += f"\nFrontend: {server.frontend}"

            channel: TextChannel = bot.get_channel(server.channel_id)

            client: CrypticClient = CrypticClient(server)

            server_running: bool = client.check_java_server()
            embed.add_field(name="**Java Server**", value=RESULT[server_running], inline=False)
            await Bot.microservice_status(server, server_running, "server")

            all_up: bool = server_running

            for expected, microservices in server.microservices.items():
                for ms in microservices:
                    ms_running: bool = server_running and client.check_microservice(ms, expected)
                    embed.add_field(name=f"**cryptic-{ms}**", value=RESULT[ms_running], inline=False)
                    all_up: bool = all_up and ms_running

                    if server_running:
                        await Bot.microservice_status(server, ms_running, "cryptic-" + ms)

            online_count: Optional[int] = None
            if server_running:
                online_count: Optional[int] = client.request({"action": "info"}).get("online")
                if online_count is not None:
                    embed.description += f"\nOnline Players: {online_count - 1}"

            client.close()

            embed.colour = [Color(0xFF0000), Color(0xFFFF00), Color(0x008800)][server_running + all_up]
            embed.set_footer(text="v1.0 - Bot by @Defelo#2022")
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


bot: Bot = Bot()
bot.run(os.environ["TOKEN"])
