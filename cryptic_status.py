import asyncio
import datetime
import json
import os
import re
from _ssl import SSLCertVerificationError
from typing import Optional, List, Dict, Set
from uuid import uuid4 as uuid

from discord import Client, Message, TextChannel, Embed, Color
from websocket import WebSocket, create_connection, WebSocketTimeoutException, WebSocketException

RESULT = [":x: Down", ":white_check_mark: Running"]
CHANNEL_CHAR = ["✘", "✔"]
SPACE = "\u2009" * 2
DOT = "\u00b7"

config = json.load(open("config.json"))
servers = config["servers"]


def validate_config():
    occupied_channels: Set[int] = set()
    for server in servers:
        channel: int = server["channel"]
        assert channel not in occupied_channels, "channel is already occupied"
        occupied_channels.add(channel)


def space_channel_name(name: str) -> str:
    return name.replace(" ", SPACE)


validate_config()


class CrypticClient:
    def __init__(self, server: dict):
        self.server: dict = server
        try:
            self.ws: WebSocket = create_connection(server["socket"])
        except (ConnectionRefusedError, ConnectionResetError, WebSocketException, SSLCertVerificationError):
            self.ws: Optional[WebSocket] = None
        else:
            self.ws.settimeout(5)

    def request(self, data: dict) -> Optional[dict]:
        for _ in range(3):
            self.ws.send(json.dumps(data))
            try:
                return json.loads(self.ws.recv())
            except WebSocketTimeoutException:
                pass

    def check_java_server(self) -> bool:
        if self.ws is None:
            return False
        response: Optional[dict] = self.request(
            {"action": "login", "name": self.server["username"], "password": self.server["password"]}
        )
        return response is not None and "token" in response

    def check_microservice(self, ms: str, expected: str) -> bool:
        response: Optional[dict] = self.request({"ms": ms, "endpoint": [], "data": {}, "tag": str(uuid())})
        # print(ms, expected, response)
        return response is not None and response.get("data", {}).get("error") == expected

    def close(self):
        if self.ws is not None:
            self.ws.send(json.dumps({"action": "logout"}))
            self.ws.close()


class Bot(Client):
    def __init__(self):
        super().__init__()

        self.status_messages: List[Message] = []

    async def on_message_delete(self, msg: Message):
        if msg.author != self.user:
            return

        for idx, message in enumerate(self.status_messages):
            if message.id == msg.id:
                break
        else:
            return

        self.status_messages[idx] = await message.channel.send(embed=message.embeds[0])

    async def on_message(self, msg: Message):
        if msg.author == self.user:
            return

        for message in self.status_messages:
            channel: TextChannel = message.channel
            if msg.channel.id == channel.id:
                break
        else:
            return

        await msg.delete()

    async def on_ready(self):
        print(f"Logged in as {self.user}")

        status_channels: Dict[int, TextChannel] = {}

        for server in servers:
            channel_id: int = server["channel"]
            if channel_id not in status_channels:
                status_channels[channel_id] = self.get_channel(channel_id)
                await status_channels[channel_id].purge(limit=None)
            self.status_messages.append(await status_channels[channel_id].send(embed=Embed(title=server["title"])))

        while True:
            for server, message in zip(servers, self.status_messages):
                # print(server)
                embed: Embed = Embed(
                    title=f"**{server['title']} - Microservice Status**", description=f"Server: {server['socket']}"
                )
                if "frontend" in server:
                    embed.description += f"\nFrontend: {server['frontend']}"

                client: CrypticClient = CrypticClient(server)

                server_running: bool = client.check_java_server()
                embed.add_field(name="**Java Server**", value=RESULT[server_running], inline=False)

                all_up: bool = server_running

                for expected, microservices in server["microservices"].items():
                    for ms in microservices:
                        ms_running: bool = server_running and client.check_microservice(ms, expected)
                        embed.add_field(name=f"**cryptic-{ms}**", value=RESULT[ms_running], inline=False)
                        all_up: bool = all_up and ms_running

                online_count: Optional[int] = None
                if server_running:
                    online_count: Optional[int] = client.request({"action": "info"}).get("online")
                    if online_count is not None:
                        embed.description += f"\nOnline Players: {online_count - 1}"

                client.close()

                embed.colour = [Color(0xFF0000), Color(0xFFFF00), Color(0x008800)][server_running + all_up]
                embed.set_footer(text="Bot by @Defelo#2022")
                embed.timestamp = datetime.datetime.utcnow()

                await message.edit(embed=embed)

                channel: TextChannel = message.channel

                old_channel_name: str = re.match(r"^.*?([a-z0-9]*)$", channel.name).group(1)
                up_indicator: str = CHANNEL_CHAR[all_up]
                new_channel_name: str = f"{up_indicator} {old_channel_name}"
                new_channel_topic: str = f"Status of {server['title']}"
                if server_running and online_count is not None:
                    new_channel_topic += f" {DOT} Online Players: {online_count - 1}"

                await channel.edit(name=space_channel_name(new_channel_name), topic=new_channel_topic)

            await asyncio.sleep(config["refresh_interval"])


Bot().run(os.environ["TOKEN"])
