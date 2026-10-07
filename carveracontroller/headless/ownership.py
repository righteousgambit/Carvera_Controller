"""Cooperative per-user endpoint ownership shared by GUI and headless clients."""

from __future__ import annotations

import hashlib
import importlib
import os
import stat
from pathlib import Path


class EndpointBusyError(RuntimeError):
    pass


class EndpointLock:
    def __init__(self, host: str, port: int, directory: Path | None = None) -> None:
        self.host, self.port = host, port
        self.directory = directory or Path.home() / ".local/state/carvera-controller/endpoint-locks"
        self.fd: int | None = None

    def acquire(self) -> None:
        if self.fd is not None:
            raise RuntimeError("Endpoint lock already held")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        mode = self.directory.lstat()
        if not stat.S_ISDIR(mode.st_mode) or (os.name != "nt" and mode.st_mode & 0o077):
            raise PermissionError("Endpoint lock directory must be private")
        name = hashlib.sha256(f"{self.host.lower()}:{self.port}".encode()).hexdigest()
        fd = os.open(self.directory / name, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or (os.name != "nt" and info.st_mode & 0o077):
                raise PermissionError("Endpoint lock must be a private regular file")
            if os.name == "nt":
                msvcrt = importlib.import_module("msvcrt")

                if info.st_size == 0:
                    os.write(fd, b"0")
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            os.close(fd)
            raise EndpointBusyError("This CNC endpoint is already owned by another local controller") from error
        except OSError as error:
            os.close(fd)
            if os.name == "nt" and error.errno in (13, 36):
                raise EndpointBusyError("This CNC endpoint is already owned by another local controller") from error
            raise
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd

    def release(self) -> None:
        if self.fd is None:
            return
        fd, self.fd = self.fd, None
        # Closing the descriptor releases flock even after a process crash.
        os.close(fd)
