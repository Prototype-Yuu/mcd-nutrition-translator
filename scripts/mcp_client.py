#!/usr/bin/env python3
"""Minimal Streamable-HTTP MCP client for McDonald's China MCP server.

Standard library only. No third-party dependencies.

Usage:
    export MCD_MCP_TOKEN=...           # required, never commit it
    python scripts/mcp_client.py list                    # tools/list
    python scripts/mcp_client.py call <tool> '<json>'    # tools/call
    python scripts/mcp_client.py raw  <json-body>        # arbitrary JSON-RPC

Design notes
------------
1. Transport: Streamable HTTP. A session id returned by ``initialize`` in the
   ``Mcp-Session-Id`` header must be echoed on every later request; the
   protocol version must be echoed in ``MCP-Protocol-Version``.
2. Response body is not guaranteed to be pure JSON. Observed shapes include
   pure JSON, an SSE stream (``data: {...}`` lines), and human-readable text
   concatenated with a JSON payload. ``parse_body`` handles all three.
3. 401 means a bad/absent token and is NOT retried. 429 and 5xx are retried
   with exponential backoff because the server is rate limited at 600 req/min.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_ENDPOINT = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "mcd-nutrition-ledger", "version": "1.0.0"}

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class McpError(RuntimeError):
    """Raised when the server returns a JSON-RPC error or an unusable body."""

    def __init__(self, message: str, *, code: Any = None, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _env_endpoint() -> str:
    return os.environ.get("MCD_MCP_ENDPOINT", DEFAULT_ENDPOINT).rstrip("/")


def _env_token() -> str:
    token = os.environ.get("MCD_MCP_TOKEN", "").strip()
    if not token:
        raise McpError(
            "MCD_MCP_TOKEN is not set. Export it first; never hardcode the token."
        )
    # Tolerate a copied "Bearer xxx" value.
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


def parse_body(raw: str) -> dict:
    """Extract the JSON-RPC envelope from a JSON / SSE / mixed-text body."""
    text = raw.strip()
    if not text:
        raise McpError("empty response body")

    # Plain JSON.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # SSE: collect `data:` payloads, use the last one that parses.
    if "data:" in text:
        payloads = [
            line[len("data:"):].strip()
            for line in text.splitlines()
            if line.strip().startswith("data:")
        ]
        for payload in reversed(payloads):
            if payload in ("", "[DONE]"):
                continue
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                continue

    # Mixed text + JSON: find each '{' and try to decode a complete object.
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and ("result" in obj or "error" in obj or "jsonrpc" in obj):
            return obj

    raise McpError(f"no JSON-RPC envelope in response: {text[:400]}")


class McpClient:
    def __init__(self, token: str | None = None, endpoint: str | None = None) -> None:
        self.endpoint = (endpoint or _env_endpoint()).rstrip("/")
        self.token = token or _env_token()
        self.session_id: str | None = None
        self.protocol_version: str | None = None
        self._next_id = 0
        self.call_count = 0

    # -- transport ---------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": CLIENT_INFO["name"],
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.protocol_version:
            headers["MCP-Protocol-Version"] = self.protocol_version
        return headers

    def _post(self, body: dict, *, retries: int = 4, timeout: int = 30) -> dict:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        delay = 1.0
        last_error: Exception | None = None

        for attempt in range(retries + 1):
            request = urllib.request.Request(
                self.endpoint, data=data, headers=self._headers(), method="POST"
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    session = response.headers.get("Mcp-Session-Id")
                    if session:
                        self.session_id = session
                    self.call_count += 1
                    raw = response.read().decode("utf-8", errors="replace")
                return parse_body(raw)
            except urllib.error.HTTPError as exc:
                status = exc.code
                detail = exc.read().decode("utf-8", errors="replace")[:400]
                last_error = McpError(
                    f"HTTP {status}: {detail}", status=status
                )
                # 401 = bad token, retrying cannot help.
                if status == 401:
                    raise McpError(
                        "HTTP 401 — MCP Token invalid, expired or missing. "
                        "Check MCD_MCP_TOKEN.",
                        status=status,
                    ) from exc
                if status not in RETRYABLE_STATUS or attempt == retries:
                    raise last_error from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
                if attempt == retries:
                    raise McpError(f"network error: {exc}") from exc

            time.sleep(delay)
            delay = min(delay * 2, 16.0)

        raise McpError(f"request failed after retries: {last_error}")

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        body = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            body["params"] = params
        response = self._post(body)
        if "error" in response:
            error = response["error"]
            raise McpError(
                error.get("message", "JSON-RPC error"), code=error.get("code")
            )
        return response.get("result", {})

    def _notify(self, method: str, params: dict | None = None) -> None:
        body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        self._post(body)

    # -- protocol ----------------------------------------------------------

    def initialize(self) -> dict:
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )
        self.protocol_version = result.get("protocolVersion", PROTOCOL_VERSION)
        try:
            self._notify("notifications/initialized")
        except McpError:
            # Some servers answer notifications with an empty body; harmless.
            pass
        return result

    def list_tools(self) -> list[dict]:
        tools: list[dict] = []
        cursor: str | None = None
        for _ in range(50):  # hard stop against a runaway cursor
            params = {"cursor": cursor} if cursor else {}
            result = self._rpc("tools/list", params)
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return tools

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        return self._rpc("tools/call", {"name": name, "arguments": arguments or {}})


def _print_json(payload: Any) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="McDonald's China MCP client")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list tools")
    sub.add_parser("init", help="run initialize handshake only")

    call = sub.add_parser("call", help="call a tool")
    call.add_argument("tool")
    call.add_argument("arguments", nargs="?", default="{}")

    raw = sub.add_parser("raw", help="send an arbitrary JSON-RPC body")
    raw.add_argument("body")

    args = parser.parse_args(argv)

    try:
        client = McpClient()
        if args.command == "init":
            _print_json(client.initialize())
        elif args.command == "list":
            client.initialize()
            tools = client.list_tools()
            _print_json(tools)
        elif args.command == "call":
            client.initialize()
            _print_json(client.call_tool(args.tool, json.loads(args.arguments)))
        elif args.command == "raw":
            client.initialize()
            _print_json(client._post(json.loads(args.body)))
    except McpError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
