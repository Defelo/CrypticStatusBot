import json
from ssl import SSLCertVerificationError
from typing import Optional
from uuid import uuid4 as uuid

from websocket import WebSocket, create_connection, WebSocketException, WebSocketTimeoutException

from server import Server


class CrypticClient:
    def __init__(self, server: Server):
        self.server: Server = server
        try:
            self.ws: WebSocket = create_connection(server.socket)
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
            {"action": "login", "name": self.server.username, "password": self.server.password}
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
