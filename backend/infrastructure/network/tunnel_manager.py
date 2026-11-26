"""Cloudflare Quick Tunnel Manager.

Architectural Guarantees:
- Strictly PID-scoped subprocess management (NEVER uses pkill -9!).
- Safe socket usage with guaranteed socket closure.
- Non-blocking RLock synchronization preventing deadlocks.
- Background asynchronous stderr reader extracting https://*.trycloudflare.com.
- Clean network watchdog monitoring tunnel health with graceful shutdown.
"""

from __future__ import annotations

import logging
import os
import re
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from backend.domain.ports import IEventBroker

logger = logging.getLogger(__name__)

TUNNEL_URL_REGEX = re.compile(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com")


def get_local_ip() -> str:
    """Detect local LAN IPv4 address for direct Wi-Fi mobile device access."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ip = str(sock.getsockname()[0])
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    finally:
        sock.close()
    return "127.0.0.1"


class CloudflareTunnelManager:
    """Manages Cloudflare Quick Tunnel lifecycle safely without pkill."""

    def __init__(
        self,
        binary_path: Optional[Path] = None,
        port: int = 8095,
        pid_file: Optional[Path] = None,
        event_broker: Optional[IEventBroker] = None,
    ) -> None:
        self.port = port
        self.binary_path = binary_path or Path(__file__).resolve().parent.parent.parent.parent / "cloudflared"
        self.pid_file = pid_file
        self.event_broker = event_broker

        self._process: Optional[subprocess.Popen[str]] = None
        self._tunnel_url: Optional[str] = None
        self._lock = threading.RLock()

        self._watchdog_thread: Optional[threading.Thread] = None
        self._watchdog_stop = threading.Event()
        self._reader_thread: Optional[threading.Thread] = None

    def start(self, timeout: float = 15.0) -> Optional[str]:
        """Alias for start_tunnel."""
        return self.start_tunnel(timeout=timeout)

    def stop(self, timeout: float = 3.0) -> None:
        """Alias for stop_tunnel."""
        self.stop_tunnel(timeout=timeout)

    def status(self) -> dict:
        """Return operational status dict."""
        with self._lock:
            running = self.is_running()
            return {
                "running": running,
                "url": self._tunnel_url if running else None,
                "pid": self._process.pid if running and self._process else None,
                "port": self.port,
                "local_url": self.get_local_url(),
                "vpn_active": self.is_vpn_active(),
            }

    def get_tunnel_url(self) -> Optional[str]:
        """Return the active tunnel URL if process is healthy."""
        with self._lock:
            if self._process and self._process.poll() is not None:
                logger.warning("Tunnel process %d exited with code %s", self._process.pid, self._process.returncode)
                self._tunnel_url = None
                self._process = None
            return self._tunnel_url

    @property
    def tunnel_url(self) -> Optional[str]:
        """Property alias for get_tunnel_url()."""
        return self.get_tunnel_url()

    @property
    def local_url(self) -> str:
        """Return LAN HTTP URL for direct Wi-Fi connection."""
        return f"http://{get_local_ip()}:{self.port}"

    def is_running(self) -> bool:
        """Check if tunnel process is actively running."""
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def start_tunnel(self, timeout: float = 15.0) -> Optional[str]:
        """Start Cloudflare Quick Tunnel process and wait for public HTTPS URL."""
        with self._lock:
            if self.is_running() and self._tunnel_url:
                return self._tunnel_url

            # Clean any previously recorded PID if stale
            self._cleanup_previous_pid()

            if not self.binary_path.exists():
                logger.warning("cloudflared binary not found at %s", self.binary_path)
                return None

            logger.info("Starting Cloudflare tunnel for 127.0.0.1:%d...", self.port)
            try:
                cmd = [
                    str(self.binary_path),
                    "tunnel",
                    "--edge-ip-version", "4",
                    "--url", f"http://127.0.0.1:{self.port}",
                ]
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )
                self._tunnel_url = None

                # Record PID
                if self.pid_file and self._process.pid:
                    try:
                        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
                        self.pid_file.write_text(str(self._process.pid), encoding="utf-8")
                    except OSError as e:
                        logger.warning("Failed to record PID to %s: %s", self.pid_file, e)

            except Exception as exc:
                logger.error("Failed to spawn cloudflared process: %s", exc)
                return None

            # Start reader thread to capture URL from stderr
            url_found_event = threading.Event()
            self._reader_thread = threading.Thread(
                target=self._read_stderr,
                args=(self._process, url_found_event),
                name="cloudflared-stderr-reader",
                daemon=True,
            )
            self._reader_thread.start()

        # Wait outside lock for URL detection
        start_time = time.time()
        while time.time() - start_time < timeout:
            if url_found_event.wait(timeout=0.2):
                break
            if not self.is_running():
                logger.error("cloudflared process terminated prematurely")
                break

        with self._lock:
            if self._tunnel_url:
                logger.info("Cloudflare tunnel active at %s", self._tunnel_url)
                self._notify_event("tunnel.started", {"url": self._tunnel_url})
            return self._tunnel_url

    def _read_stderr(self, proc: subprocess.Popen[str], url_event: threading.Event) -> None:
        """Background loop parsing cloudflared stderr for trycloudflare.com URL."""
        if not proc.stderr:
            return

        try:
            for line in proc.stderr:
                if not line:
                    break
                match = TUNNEL_URL_REGEX.search(line)
                if match:
                    with self._lock:
                        self._tunnel_url = match.group(0)
                    url_event.set()
                    logger.debug("Captured tunnel URL: %s", self._tunnel_url)
        except Exception as e:
            logger.debug("Stderr reader terminated: %s", e)

    def stop_tunnel(self, timeout: float = 3.0) -> None:
        """Safely terminate only the managed cloudflared process by PID."""
        self.stop_watchdog()

        with self._lock:
            proc = self._process
            self._process = None
            self._tunnel_url = None

            if not proc:
                self._cleanup_previous_pid()
                return

            pid = proc.pid
            logger.info("Stopping Cloudflare tunnel process (PID %d)...", pid)

            try:
                proc.terminate()
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    logger.warning("PID %d did not terminate gracefully; sending SIGKILL", pid)
                    proc.kill()
                    proc.wait(timeout=1.0)
            except ProcessLookupError:
                pass
            except Exception as e:
                logger.warning("Error stopping process %d: %s", pid, e)
            finally:
                stderr = getattr(proc, "stderr", None)
                if stderr:
                    try:
                        stderr.close()
                    except Exception:
                        pass
                self._cleanup_previous_pid()

            self._notify_event("tunnel.stopped", {"pid": pid})

    def _cleanup_previous_pid(self) -> None:
        """Terminate previously recorded PID from file if still alive."""
        if not self.pid_file or not self.pid_file.is_file():
            return
        try:
            raw_pid = self.pid_file.read_text(encoding="utf-8").strip()
            if raw_pid.isdigit():
                pid = int(raw_pid)
                if self._process and self._process.pid == pid:
                    return  # Currently managed active process
                # Check if process is still alive
                try:
                    os.kill(pid, 0)
                    logger.info("Terminating orphaned cloudflared PID %d from previous run", pid)
                    os.kill(pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
            self.pid_file.unlink(missing_ok=True)
        except Exception as e:
            logger.debug("Cleanup PID error: %s", e)

    def get_local_ip(self) -> str:
        """Determine local Wi-Fi / LAN IP with guaranteed socket closure."""
        # 1. Try macOS ipconfig
        for iface in ("en0", "en1", "en2"):
            try:
                out = subprocess.check_output(
                    ["ipconfig", "getifaddr", iface],
                    text=True,
                    timeout=1.0,
                ).strip()
                if out:
                    return out
            except Exception:
                pass

        # 2. Safe UDP socket connect (does not transmit packets)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(1.0)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                return str(ip)
        except Exception:
            return "127.0.0.1"

    def get_local_url(self) -> str:
        """Local LAN URL for mobile connections on same Wi-Fi network."""
        return f"http://{self.get_local_ip()}:{self.port}"

    def is_vpn_active(self) -> bool:
        """Check if active VPN (utun interface) is routing default traffic."""
        try:
            out = subprocess.check_output(["netstat", "-rn"], text=True, timeout=2.0)
            return any("utun" in line and "default" in line for line in out.splitlines())
        except Exception:
            return False

    def start_watchdog(self, interval_seconds: float = 5.0) -> None:
        """Start background network health watchdog."""
        with self._lock:
            if self._watchdog_thread and self._watchdog_thread.is_alive():
                return
            self._watchdog_stop.clear()
            self._watchdog_thread = threading.Thread(
                target=self._watchdog_loop,
                args=(interval_seconds,),
                name="tunnel-watchdog",
                daemon=True,
            )
            self._watchdog_thread.start()

    def _watchdog_loop(self, interval: float) -> None:
        while not self._watchdog_stop.is_set():
            with self._lock:
                if self._process and self._process.poll() is not None:
                    logger.warning("Tunnel died unexpectedly. Triggering restart...")
                    self._process = None
                    self._tunnel_url = None
                    self._notify_event("tunnel.crashed", {})

            self._watchdog_stop.wait(interval)

    def stop_watchdog(self) -> None:
        """Stop background watchdog thread."""
        self._watchdog_stop.set()
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=2.0)
            self._watchdog_thread = None

    def _notify_event(self, event_type: str, data: dict) -> None:
        if self.event_broker:
            try:
                self.event_broker.publish(event_type, data)
            except Exception as e:
                logger.warning("Event dispatch failed for %s: %s", event_type, e)
