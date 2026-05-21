from __future__ import annotations

import logging
import socket
import threading
import time

import paramiko

from frigate_protect_events.config import ProtectConfig

log = logging.getLogger(__name__)


class SshTunnel:
    """ssh port forward to the protect console's local postgres."""

    def __init__(self, config: ProtectConfig) -> None:
        self._config = config
        self._client: paramiko.SSHClient | None = None
        self._transport: paramiko.Transport | None = None
        self._local_port: int | None = None
        self._forward_thread: threading.Thread | None = None
        self._running = False

    @property
    def local_port(self) -> int:
        if self._local_port is None:
            raise RuntimeError("tunnel not connected")
        return self._local_port

    def connect(self) -> int:
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._client.connect(
            hostname=self._config.host,
            port=self._config.ssh_port,
            username=self._config.ssh_user,
            key_filename=self._config.ssh_key,
        )
        self._transport = self._client.get_transport()

        # bind a local port
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        self._local_port = server.getsockname()[1]
        server.listen(1)
        server.settimeout(1.0)

        self._running = True
        self._forward_thread = threading.Thread(
            target=self._forward_loop,
            args=(server,),
            daemon=True,
        )
        self._forward_thread.start()

        log.info(
            "ssh tunnel open: 127.0.0.1:%d -> %s:%d",
            self._local_port,
            self._config.host,
            self._config.db_port,
        )
        return self._local_port

    def _forward_loop(self, server: socket.socket) -> None:
        while self._running:
            try:
                client_sock, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                channel = self._transport.open_channel(
                    "direct-tcpip",
                    ("/run/postgresql", self._config.db_port),
                    client_sock.getpeername(),
                )
            except Exception:
                log.exception("failed to open ssh channel")
                client_sock.close()
                continue

            if channel is None:
                client_sock.close()
                continue

            # bidirectional relay
            t = threading.Thread(
                target=self._relay, args=(client_sock, channel), daemon=True
            )
            t.start()

    def _relay(self, sock: socket.socket, channel: paramiko.Channel) -> None:
        try:
            while True:
                r = channel.recv(4096)
                if not r:
                    break
                sock.sendall(r)

                if sock.fileno() == -1:
                    break
                s = sock.recv(4096)
                if not s:
                    break
                channel.sendall(s)
        except Exception:
            pass
        finally:
            channel.close()
            sock.close()

    def close(self) -> None:
        self._running = False
        if self._client:
            self._client.close()
        log.info("ssh tunnel closed")

    def __enter__(self) -> SshTunnel:
        self.connect()
        return self

    def __exit__(self, *args) -> None:
        self.close()
