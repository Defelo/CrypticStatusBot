from typing import Optional, Dict, List, Tuple


class Server:
    def __init__(
        self,
        channel_id: int,
        title: str,
        frontend: Optional[str],
        socket: str,
        username: str,
        password: str,
        microservices: Dict[str, List[str]],
    ):
        self.channel_id: int = channel_id
        self.title: str = title
        self.frontend: Optional[str] = frontend
        self.socket: str = socket
        self.username: str = username
        self.password: str = password
        self.microservices: Dict[str, List[str]] = microservices

        self.ms_down: Dict[str, Tuple[float, Optional[int]]] = {}

    @staticmethod
    def deserialize(data: dict) -> "Server":
        return Server(
            data.get("channel"),
            data.get("title"),
            data.get("frontend"),
            data.get("socket"),
            data.get("username"),
            data.get("password"),
            data.get("microservices"),
        )
