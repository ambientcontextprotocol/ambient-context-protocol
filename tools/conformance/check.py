#!/usr/bin/env python3
"""An outside check for an Ambient Context Protocol provider, version 0.2.3.

Given a provider's descriptor file, or its endpoint and token, this script
sends the provider requests and reports every requirement of docs/pm.md
that can be judged from the answers alone. One line per check:

    PASS|FAIL|WARN|SKIP  PR-nnn  short-name  detail

It exits 1 when any check fails. WARN marks a "should" the provider does
not meet; SKIP marks a check that did not apply or could not be run.

Nothing private is printed: no token, and no element's title, content,
url or attributes. A result holds ids, roles, counts and status codes.

Usage:
    python3 tools/conformance/check.py <descriptor.json>
    python3 tools/conformance/check.py --endpoint URL --token T [--instance I] [--pid N]
    python3 tools/conformance/check.py <descriptor.json> --watch-hold 20

A provider's own test can reuse the watch client here, and the three
helpers that need the app driven while a watch is open:

    with check.Watch.from_descriptor(path) as watch:
        check.drive_changes(watch, select_another_paragraph, results)
        check.drive_hover(watch, move_the_pointer, results)
        check.drive_stop(watch, turn_the_provider_off, results)

Python 3 standard library only.
"""
import argparse
import codecs
import http.client
import json
import os
import re
import secrets
import socket
import stat
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

PROTOCOL = "0.2.3"
MCP_VERSION = "2026-07-28"
LEGACY_VERSION = "2025-11-25"
EXTENSION = "io.github.ambientcontextprotocol/context"
CURRENT_URI = "ambient://current"
LOCATION_TEMPLATE = "ambient://location/{id}"
LOCATION_PREFIX = "ambient://location/"
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_SUBSCRIPTION = "io.modelcontextprotocol/subscriptionId"
LISTEN = "subscriptions/listen"
ACKNOWLEDGED = "notifications/subscriptions/acknowledged"
UPDATED = "notifications/resources/updated"
# Section 9.1: at most one notice in any 250 ms on a watch, and a comment
# line on a quiet one at least every 15 seconds. The tolerances allow for
# the scheduling of two programs on one machine.
COALESCE = 0.25
COALESCE_TOLERANCE = 0.05
KEEPALIVE = 15.0
KEEPALIVE_TOLERANCE = 0.25
HEAD_LIMIT = 1 << 16
BODY_LIMIT = 1 << 20

ROLES = (
    "Application", "Window", "Group", "List", "Table", "Row", "Cell",
    "Text", "Heading", "Link", "Image", "Page", "Document",
)
ID_FORM = re.compile(r"\A[A-Za-z0-9_-]{1,128}\Z")
BLOCK_FIELDS = {
    "text": ("text",),
    "image": ("data", "mimeType"),
    "audio": ("data", "mimeType"),
    "resource_link": ("uri", "name"),
    "resource": ("resource",),
}
LOCATION_STATES = ("visible", "offscreen", "gone")
EDGES = ("left", "right", "top", "bottom")
DESCRIPTOR_FIELDS = ("protocol", "app", "pid", "instance", "endpoint", "token", "started")
LOOPBACK_NAMES = ("127.0.0.1", "localhost", "::1")
STARTED_FORM = re.compile(r"\A\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z\Z")
# A word a provider chose is printed only when it looks like a word.
PRINTABLE_WORD = re.compile(r"\A[A-Za-z0-9_.-]{1,40}\Z")

PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"
OMIT = object()


# ---------------------------------------------------------------- results

class Results:
    def __init__(self):
        self.items = []

    def add(self, status, requirement, name, detail=""):
        self.items.append({"status": status, "requirement": requirement, "name": name, "detail": detail})

    def judge(self, requirement, name, problems, passed=""):
        """PASS with `passed`, or FAIL listing the first few problems."""
        if problems:
            self.add(FAIL, requirement, name, summarize(problems))
        else:
            self.add(PASS, requirement, name, passed)

    def count(self, status):
        return sum(1 for item in self.items if item["status"] == status)

    @property
    def failed(self):
        return self.count(FAIL) > 0


def summarize(problems, limit=4):
    shown = "; ".join(problems[:limit])
    if len(problems) > limit:
        shown += "; and %d more" % (len(problems) - limit)
    return shown


def printable(word):
    """A provider's word, if it is safe to print, or a placeholder."""
    if isinstance(word, str) and PRINTABLE_WORD.match(word):
        return "'%s'" % word
    return "(a value not printed)"


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ------------------------------------------------------------------- HTTP

class Response:
    """One HTTP response, or the reason there was none."""

    def __init__(self, status=None, headers=(), body=b"", failure=None, seconds=0.0):
        self.status = status
        self.headers = list(headers)
        self.body = body
        self.failure = failure
        self.seconds = seconds
        self._json = OMIT

    def header(self, name):
        for key, value in self.headers:
            if key.lower() == name.lower():
                return value
        return None

    def json(self):
        if self._json is OMIT:
            self._json = None
            text = None
            try:
                text = self.body.decode("utf-8")
            except UnicodeDecodeError:
                pass
            if text is not None and (self.header("content-type") or "").lower().startswith("text/event-stream"):
                text = first_event(text)
            if text:
                try:
                    self._json = json.loads(text)
                except ValueError:
                    pass
        return self._json

    def error_code(self):
        message = self.json()
        if isinstance(message, dict) and isinstance(message.get("error"), dict):
            code = message["error"].get("code")
            if isinstance(code, int) and not isinstance(code, bool):
                return code
        return None

    def result(self):
        message = self.json()
        if isinstance(message, dict) and isinstance(message.get("result"), dict) and "error" not in message:
            return message["result"]
        return None

    def describe(self):
        """What came back, in status codes only."""
        if self.failure:
            return "no response (%s)" % self.failure
        code = self.error_code()
        if code is not None:
            return "HTTP %d, error %d" % (self.status, code)
        if self.result() is not None:
            return "HTTP %d, a result" % self.status
        if not self.body:
            return "HTTP %d, no body" % self.status
        return "HTTP %d, a body that is not a JSON-RPC answer" % self.status

    def refused_with(self, status, code):
        return self.status == status and self.error_code() == code


def first_event(text):
    """The data of the first event in an event stream."""
    lines = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith("data:"):
            lines.append(line[5:].lstrip(" "))
        elif not line and lines:
            break
    return "\n".join(lines)


class Client:
    """Sends requests to one endpoint and keeps every response's headers."""

    def __init__(self, host, port, path, token, timeout):
        self.host, self.port, self.path, self.token, self.timeout = host, port, path, token, timeout
        self.seen = []
        self._next_id = 0

    def send(self, http_method, headers, body=None, declared_length=None, timeout=None):
        """One request on a fresh connection. Redirects are not followed."""
        started = time.monotonic()
        connection = http.client.HTTPConnection(self.host, self.port, timeout=timeout or self.timeout)
        try:
            connection.putrequest(http_method, self.path)
            for name, value in headers.items():
                connection.putheader(name, value)
            if declared_length is not None:
                connection.putheader("Content-Length", str(declared_length))
                connection.endheaders()
            elif body is not None:
                connection.putheader("Content-Length", str(len(body)))
                connection.endheaders(body)
            else:
                connection.endheaders()
            raw = connection.getresponse()
            response = Response(raw.status, raw.getheaders(), raw.read(), seconds=time.monotonic() - started)
        except (OSError, http.client.HTTPException) as error:
            reason = "timed out" if isinstance(error, socket.timeout) else type(error).__name__
            response = Response(failure=reason, seconds=time.monotonic() - started)
        finally:
            connection.close()
        self.seen.append(response)
        return response

    def rpc(self, method, params=None, *, token=OMIT, version=MCP_VERSION, header_version=OMIT,
            capabilities=OMIT, method_header=OMIT, name_header=OMIT, extra_headers=None,
            http_method="POST", raw_body=None):
        """A JSON-RPC request as a current client sends it.

        Each part can be overridden, or left out with None, the way the
        packages' own tests form requests.
        """
        params = dict(params or {})
        meta = {}
        if version is not None:
            meta[META_VERSION] = version
        if capabilities is OMIT:
            capabilities = {}
        if capabilities is not None:
            meta[META_CAPABILITIES] = capabilities
        if meta:
            params["_meta"] = meta
        self._next_id += 1
        message = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params}

        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if token is OMIT:
            token = self.token
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if header_version is OMIT:
            header_version = version
        if header_version is not None:
            headers["MCP-Protocol-Version"] = header_version
        if method_header is OMIT:
            method_header = method
        if method_header is not None:
            headers["Mcp-Method"] = method_header
        if name_header is OMIT:
            name_header = params.get("uri")
        if name_header is not None:
            headers["Mcp-Name"] = name_header
        headers.update(extra_headers or {})
        body = raw_body if raw_body is not None else json.dumps(message).encode("utf-8")
        return self.send(http_method, headers, body)

    def legacy(self, method, params=None, header=LEGACY_VERSION):
        """A request as a client on an earlier MCP revision sends it."""
        self._next_id += 1
        message = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": dict(params or {})}
        headers = {
            "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer " + self.token,
        }
        if header is not None:
            headers["MCP-Protocol-Version"] = header
        return self.send("POST", headers, json.dumps(message).encode("utf-8"))


    def watch(self, notifications=None, *, token=OMIT, extra_headers=None):
        """Opens a watch as a host does, and keeps its response's headers."""
        self._next_id += 1
        watch = Watch(self.host, self.port, self.path, self.token if token is OMIT else token,
                      timeout=self.timeout, notifications=notifications, request_id=self._next_id,
                      headers=extra_headers).open()
        self.seen.append(watch.response)
        return watch


# ------------------------------------------------------------- the watch

class Event:
    """One thing read from a watch's stream, and when.

    `kind` is "comment", "message" (a JSON object, in `message`) or
    "invalid" (data that is not a JSON object). `at` is time.monotonic()
    when its last byte arrived.
    """
    __slots__ = ("kind", "at", "message")

    def __init__(self, kind, at, message=None):
        self.kind, self.at, self.message = kind, at, message

    @property
    def method(self):
        return self.message.get("method") if self.kind == "message" else None


class Framing:
    """Takes a response body out of its HTTP framing, a piece at a time."""

    def __init__(self, chunked, length):
        self.chunked, self.remaining = chunked, length
        self.buffer, self.left = b"", 0

    def feed(self, data):
        """Returns (the body bytes in `data`, whether the body is complete)."""
        if not self.chunked:
            if self.remaining is None:
                return data, False  # The body ends when the connection does.
            data = data[:self.remaining]
            self.remaining -= len(data)
            return data, self.remaining == 0
        self.buffer += data
        out = []
        while True:
            if self.left == 0:
                end = self.buffer.find(b"\r\n")
                if end < 0:
                    return b"".join(out), False
                line, self.buffer = self.buffer[:end], self.buffer[end + 2:]
                if not line:
                    continue  # The line break that closes a chunk.
                self.left = int(line.split(b";")[0].strip(), 16)
                if self.left == 0:
                    return b"".join(out), True
            piece = self.buffer[:self.left]
            if not piece:
                return b"".join(out), False
            out.append(piece)
            self.buffer = self.buffer[len(piece):]
            self.left -= len(piece)


class Watch:
    """A client for one watch: `subscriptions/listen`, held open (section 7.7).

    `open()` sends the request and reads the response's head. If the answer
    is an event stream, `streaming` is true and a thread reads events into
    `events`, each stamped as it arrives, until the stream ends or
    `close()` is called. Otherwise `response` holds the whole answer.

    Nothing here prints. A caller reports counts and times, never a
    message's contents.
    """

    def __init__(self, host, port, path, token, *, timeout=5.0, notifications=None, request_id=1, headers=None):
        self.host, self.port, self.path, self.token, self.timeout = host, port, path, token, timeout
        self.notifications = {"resourceSubscriptions": [CURRENT_URI]} if notifications is None else notifications
        self.request_id = request_id
        self.extra_headers = dict(headers or {})
        self.response = Response(failure="not opened")
        self.streaming = False
        self.opened_at = None
        self.ended = False
        self.ended_at = None
        self.failure = None  # Why the stream ended, when it was not closed in order.
        self.events = []
        self._changed = threading.Condition()
        self._socket = None
        self._reader = None
        self._closing = False
        self._framing = None
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._text = ""
        self._data = []

    @classmethod
    def at(cls, endpoint, token, **options):
        """A watch on an endpoint on this machine. The token goes nowhere else."""
        host, port, path, _address, _path = parse_endpoint(endpoint)
        if host not in LOOPBACK_NAMES or port is None or not path:
            raise ValueError("the endpoint is not an address on this machine")
        if "?" in endpoint:
            path += "?" + urlsplit(endpoint).query
        return cls(host, port, path, token, **options)

    @classmethod
    def from_descriptor(cls, descriptor_path, **options):
        with open(descriptor_path, "rb") as handle:
            descriptor = json.loads(handle.read().decode("utf-8"))
        return cls.at(descriptor.get("endpoint"), descriptor.get("token"), **options)

    def __enter__(self):
        return self.open() if self.response.failure == "not opened" else self

    def __exit__(self, *_):
        self.close()

    # -- opening

    def open(self):
        """Sends the request. Returns the watch; see `streaming` and `response`."""
        body = json.dumps({"jsonrpc": "2.0", "id": self.request_id, "method": LISTEN, "params": {
            "_meta": {META_VERSION: MCP_VERSION, META_CAPABILITIES: {}},
            "notifications": self.notifications,
        }}).encode("utf-8")
        headers = {
            "Host": "%s:%d" % (self.host, self.port), "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": MCP_VERSION,
            "Mcp-Method": LISTEN, "Content-Length": str(len(body)), "Connection": "close",
        }
        if self.token is not None:
            headers["Authorization"] = "Bearer " + self.token
        headers.update(self.extra_headers)
        request = "POST %s HTTP/1.1\r\n" % self.path + "".join("%s: %s\r\n" % pair for pair in headers.items()) + "\r\n"

        started = time.monotonic()
        deadline = started + self.timeout
        connection = None
        try:
            connection = socket.create_connection((self.host, self.port), timeout=self.timeout)
            connection.sendall(request.encode("latin-1") + body)
            head, rest = self._read_head(connection, deadline)
            status, found = self._parse_head(head)
            named = {name.lower(): value for name, value in found}
            encoding = named.get("transfer-encoding", "").lower()
            length = named.get("content-length")
            self._framing = Framing("chunked" in encoding, int(length) if length is not None and not encoding else None)
            if status == 200 and named.get("content-type", "").lower().startswith("text/event-stream"):
                self.response = Response(status, found, seconds=time.monotonic() - started)
                self.streaming = True
                self.opened_at = time.monotonic()
                connection.settimeout(None)
                self._socket = connection
                self._reader = threading.Thread(target=self._read, args=(connection, rest), daemon=True)
                self._reader.start()
                return self
            whole = self._read_body(connection, rest, deadline)
            self.response = Response(status, found, whole, seconds=time.monotonic() - started)
        except (OSError, ValueError) as error:
            reason = "timed out" if isinstance(error, socket.timeout) else type(error).__name__
            self.response = Response(failure=reason, seconds=time.monotonic() - started)
        if connection is not None:
            connection.close()
        self.ended, self.ended_at = True, time.monotonic()
        return self

    @staticmethod
    def _receive(connection, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise socket.timeout()
        connection.settimeout(remaining)
        return connection.recv(65536)

    def _read_head(self, connection, deadline):
        data = b""
        while b"\r\n\r\n" not in data:
            if len(data) > HEAD_LIMIT:
                raise ValueError("the response's head is too long")
            piece = self._receive(connection, deadline)
            if not piece:
                raise ConnectionError("closed before a response")
            data += piece
        head, _separator, rest = data.partition(b"\r\n\r\n")
        return head, rest

    @staticmethod
    def _parse_head(head):
        lines = head.decode("latin-1").split("\r\n")
        parts = lines[0].split(" ", 2)
        if len(parts) < 2 or not parts[0].startswith("HTTP/"):
            raise ValueError("not an HTTP response")
        found = []
        for line in lines[1:]:
            name, separator, value = line.partition(":")
            if separator:
                found.append((name.strip(), value.strip()))
        return int(parts[1]), found

    def _read_body(self, connection, rest, deadline):
        """The whole body of an answer that is not a stream, within limits."""
        whole, data = b"", rest
        while True:
            piece, complete = self._framing.feed(data) if data else (b"", self._framing.remaining == 0)
            whole += piece
            if complete or len(whole) > BODY_LIMIT:
                return whole
            try:
                data = self._receive(connection, deadline)
            except socket.timeout:
                return whole
            if not data:
                return whole

    # -- reading

    def _read(self, connection, data):
        try:
            while True:
                if data:
                    now = time.monotonic()
                    piece, complete = self._framing.feed(data)
                    self._parse(piece, now)
                    if complete:
                        break
                data = connection.recv(65536)
                if not data:
                    break
        except (OSError, ValueError) as error:
            if not self._closing:
                self.failure = type(error).__name__
        with self._changed:
            self.ended, self.ended_at = True, time.monotonic()
            self._changed.notify_all()

    def _parse(self, data, now):
        self._text += self._decoder.decode(data)
        while "\n" in self._text:
            line, self._text = self._text.split("\n", 1)
            line = line.rstrip("\r")
            if line.startswith(":"):
                self._add(Event("comment", now))
            elif line.startswith("data:"):
                self._data.append(line[5:][1:] if line[5:6] == " " else line[5:])
            elif not line and self._data:
                text, self._data = "\n".join(self._data), []
                try:
                    message = json.loads(text)
                except ValueError:
                    message = None
                self._add(Event("message", now, message) if isinstance(message, dict) else Event("invalid", now))

    def _add(self, event):
        with self._changed:
            self.events.append(event)
            self._changed.notify_all()

    # -- what was seen

    def snapshot(self):
        with self._changed:
            return list(self.events)

    def messages(self):
        """The events that are not comments, in order."""
        return [event for event in self.snapshot() if event.kind != "comment"]

    def first_message(self, timeout=None):
        """The first message on the stream, waiting for it, or None."""
        self._wait(lambda: any(event.kind != "comment" for event in self.events), timeout)
        found = self.messages()
        return found[0] if found else None

    def notice_times(self, since=None):
        """When each `notifications/resources/updated` arrived, from `since` on."""
        return [event.at for event in self.snapshot()
                if event.method == UPDATED and (since is None or event.at >= since)]

    def wait_notice(self, since, timeout):
        """When the first notice at or after `since` arrived, or None."""
        self._wait(lambda: any(event.method == UPDATED and event.at >= since for event in self.events), timeout)
        found = self.notice_times(since)
        return found[0] if found else None

    def collect(self, seconds):
        """Lets the stream run for `seconds`, or until it ends."""
        self.wait_end(seconds)

    def wait_end(self, timeout):
        """Whether the stream has ended, waiting up to `timeout` for it."""
        self._wait(lambda: False, timeout)
        return self.ended

    @property
    def completed(self):
        """Whether the provider ended the watch with a completion result."""
        return any(is_completion(event, self.request_id) for event in self.snapshot())

    def _wait(self, test, timeout):
        """Until `test` holds, the stream ends or `timeout` passes."""
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        with self._changed:
            while not self.ended and not test():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                self._changed.wait(remaining)

    def close(self):
        """Ends the watch from the host's side."""
        self._closing = True
        if self._socket is not None:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._socket.close()
            self._socket = None
        if self._reader is not None:
            self._reader.join(1.0)
            self._reader = None


def is_completion(event, subscription):
    if event.kind != "message" or "method" in event.message or not same_id(event.message.get("id"), subscription):
        return False
    result = event.message.get("result")
    return isinstance(result, dict) and result.get("resultType") == "complete"


def same_id(found, expected):
    return type(found) is type(expected) and found == expected


def several(count, word):
    return "%d %s%s" % (count, word, "" if count == 1 else "s")


def acknowledgment_problems(event, subscription):
    """What is wrong with a watch's first message (section 7.7). Counts only."""
    if event is None:
        return ["no message arrived on the stream"]
    if event.kind != "message":
        return ["the first message is not a JSON object"]
    if event.method == UPDATED:
        return ["the first message is a notice, not the acknowledgment"]
    if event.method != ACKNOWLEDGED:
        return ["the first message is not the acknowledgment"]
    params = event.message.get("params")
    if not isinstance(params, dict):
        return ["the acknowledgment has no params"]
    problems = []
    meta = params.get("_meta")
    if not isinstance(meta, dict) or not same_id(meta.get(META_SUBSCRIPTION), subscription):
        problems.append("its subscription id is not the request's id")
    agreed = params.get("notifications")
    if not isinstance(agreed, dict):
        return problems + ["it names no filter"]
    addresses = agreed.get("resourceSubscriptions")
    if not isinstance(addresses, list):
        problems.append("its resourceSubscriptions is not a list")
    elif addresses != [CURRENT_URI]:
        others = sum(1 for address in addresses if address != CURRENT_URI)
        if others:
            problems.append("it names %s beside %s" % (several(others, "address"), CURRENT_URI)
                            if CURRENT_URI in addresses else "it does not name %s" % CURRENT_URI)
        else:
            problems.append("it names %s %d times" % (CURRENT_URI, len(addresses)))
    more = sum(1 for name, value in agreed.items() if name != "resourceSubscriptions" and value)
    if more:
        problems.append("it agrees to %s of notification beside resource updates" % several(more, "other kind"))
    return problems


def notice_problems(message, subscription):
    """What is wrong with a notice (PR-082). Counts fields; quotes nothing."""
    problems = []
    extra = len(set(message) - {"jsonrpc", "method", "params"})
    if extra:
        problems.append("%s beside jsonrpc, method and params" % several(extra, "extra field"))
    params = message.get("params")
    if not isinstance(params, dict):
        return problems + ["params is not an object"]
    if params.get("uri") != CURRENT_URI:
        problems.append("its uri is not %s" % CURRENT_URI)
    extra = len(set(params) - {"uri", "_meta"})
    if extra:
        problems.append("%s in params beside uri and _meta" % several(extra, "extra field"))
    meta = params.get("_meta")
    if not isinstance(meta, dict) or not same_id(meta.get(META_SUBSCRIPTION), subscription):
        problems.append("its subscription id is not the request's id")
    elif len(meta) > 1:
        problems.append("%s in _meta beside the subscription id" % several(len(meta) - 1, "extra field"))
    return problems


def stream_problems(events, subscription):
    """Everything on a watch's stream that the host did not ask for.

    Returns (problems, number of notices). The first message is judged by
    `acknowledgment_problems`; here it only has to be one of the kinds
    a watch may carry.
    """
    problems, notices, position = [], 0, 0
    for event in events:
        if event.kind == "comment":
            continue
        position += 1
        if event.kind != "message":
            problems.append("message %d is not a JSON object" % position)
        elif event.method == UPDATED:
            notices += 1
            problems += ["notice %d: %s" % (notices, problem) for problem in notice_problems(event.message, subscription)]
        elif event.method == ACKNOWLEDGED:
            if position != 1:
                problems.append("message %d is a second acknowledgment" % position)
        elif is_completion(event, subscription):
            pass
        elif "method" in event.message:
            problems.append("message %d is a notification of a type that was not asked for" % position)
        else:
            problems.append("message %d is a response that is not this watch's completion" % position)
    return problems, notices


def closest(times):
    """The smallest gap between consecutive times, or None."""
    gaps = [later - earlier for earlier, later in zip(times, times[1:])]
    return min(gaps) if gaps else None


def coalescing_result(times, name="watch-coalesced"):
    """PR-083's first half, on the notices that were seen."""
    if not times:
        return PASS, "PR-083", name, "no change happened while watching, so no notice was seen"
    gap = closest(times)
    limit = COALESCE - COALESCE_TOLERANCE
    if gap is not None and gap < limit:
        near = sum(1 for earlier, later in zip(times, times[1:]) if later - earlier < limit)
        return FAIL, "PR-083", name, "%s, %d of them less than %d ms after the one before; the closest %d ms" % (
            several(len(times), "notice"), near, int(COALESCE * 1000), int(gap * 1000))
    if gap is None:
        return PASS, "PR-083", name, "1 notice seen"
    return PASS, "PR-083", name, "%d notices, none closer than %d ms" % (len(times), int(gap * 1000))


# ---------------------------------------------------------- the descriptor

def parse_endpoint(endpoint):
    """Splits an endpoint and lists what is wrong with its address and path.

    Returns (host, port, path, address_problems, path_problems).
    """
    address, path_problems = [], []
    if not isinstance(endpoint, str):
        return None, None, None, ["the endpoint is not a string"], []
    try:
        parts = urlsplit(endpoint)
        host, port = parts.hostname, parts.port
    except ValueError:
        return None, None, None, ["the endpoint is not a URL"], []
    if parts.scheme != "http":
        address.append("the scheme is not http")
    if host != "127.0.0.1":
        address.append("the host is not 127.0.0.1")
    if port is None:
        address.append("no port is given")
    if parts.username is not None or parts.password is not None:
        address.append("the address carries user information")
    path = parts.path
    if not path.startswith("/"):
        path_problems.append("the path does not begin with /")
    if "?" in endpoint:
        path_problems.append("the endpoint has a query")
    if "#" in endpoint:
        path_problems.append("the endpoint has a fragment")
    return host, port, path, address, path_problems


def started_by(pid, parent):
    """Whether the process `parent` started the process `pid`."""
    try:
        found = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
        actual = int(found.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return SKIP, "PR-093", "descriptor-for", "could not ask the system (%s)" % type(error).__name__
    if actual != parent:
        return FAIL, "PR-093", "descriptor-for", "the provider was not started by the process 'for' names"
    return PASS, "PR-093", "descriptor-for", "the provider was started by the app it answers for"


def via_result(root):
    """PR-096: the root of a provider that answers for another app says how
    it learned what it reports."""
    if not isinstance(root, dict):
        return SKIP, "PR-096", "root-via", "no root to check"
    attributes = root.get("attributes")
    via = attributes.get("via") if isinstance(attributes, dict) else None
    if isinstance(via, str) and via:
        return PASS, "PR-096", "root-via", "the root says it is second-hand: %s" % printable(via)
    return FAIL, "PR-096", "root-via", "the descriptor has 'for' and the root has no 'via' attribute"


def check_descriptor_file(path, results):
    """Reads a descriptor and checks the file. Returns the descriptor or None."""
    try:
        with open(path, "rb") as handle:
            descriptor = json.loads(handle.read().decode("utf-8"))
    except (OSError, ValueError) as error:
        results.add(FAIL, "PR-018", "descriptor-fields", "the file could not be read as JSON (%s)" % type(error).__name__)
        return None
    if not isinstance(descriptor, dict):
        results.add(FAIL, "PR-018", "descriptor-fields", "the file does not hold a JSON object")
        return None

    problems = ["'%s' is missing" % name for name in DESCRIPTOR_FIELDS if name not in descriptor]
    for name in ("protocol", "instance", "endpoint", "token", "started"):
        if name in descriptor and not (isinstance(descriptor[name], str) and descriptor[name]):
            problems.append("'%s' is not a non-empty string" % name)
    pid = descriptor.get("pid")
    if "pid" in descriptor and not (isinstance(pid, int) and not isinstance(pid, bool) and pid > 0):
        problems.append("'pid' is not a positive whole number")
    app = descriptor.get("app")
    if "app" in descriptor:
        if not isinstance(app, dict):
            problems.append("'app' is not an object")
        else:
            for name in ("id", "name", "version"):
                if not (isinstance(app.get(name), str) and app.get(name)):
                    problems.append("'app.%s' is missing or not a string" % name)
    started = descriptor.get("started")
    if isinstance(started, str) and started and not STARTED_FORM.match(started):
        problems.append("'started' is not a UTC time such as 2026-11-09T21:14:03Z")
    results.judge("PR-018", "descriptor-fields", problems, "the seven fields are present")

    # A provider that answers for another app (RFC-0004) names that app
    # in 'for', and its file after that app and then itself.
    target = descriptor.get("for")
    if target is not None:
        target_ok = (
            isinstance(target, dict) and isinstance(target.get("id"), str) and target.get("id")
            and isinstance(target.get("pid"), int) and not isinstance(target.get("pid"), bool) and target["pid"] > 0
        )
        if not target_ok:
            results.add(FAIL, "PR-093", "descriptor-for", "'for' is not an object with a string 'id' and a positive 'pid'")
        elif not isinstance(pid, int):
            results.add(SKIP, "PR-093", "descriptor-for", "pid is unusable")
        elif target["pid"] == pid:
            results.add(FAIL, "PR-093", "descriptor-for", "'for.pid' is the provider's own pid")
        else:
            expected = "%s.%d.for.%d.json" % (target["id"], target["pid"], pid)
            if os.path.basename(path) == expected:
                results.add(PASS, "PR-017", "descriptor-name", "<app-id>.<app-pid>.for.<pid>.json")
            else:
                results.add(FAIL, "PR-017", "descriptor-name", "the file is not named <app-id>.<app-pid>.for.<pid>.json after 'for' and its own pid")
            results.add(*started_by(pid, target["pid"]))
    elif isinstance(app, dict) and isinstance(app.get("id"), str) and isinstance(pid, int):
        expected = "%s.%d.json" % (app["id"], pid)
        if os.path.basename(path) == expected:
            results.add(PASS, "PR-017", "descriptor-name", "<bundle-id>.<pid>.json")
        else:
            results.add(FAIL, "PR-017", "descriptor-name", "the file is not named <bundle-id>.<pid>.json after its own app.id and pid")
    else:
        results.add(SKIP, "PR-017", "descriptor-name", "app.id or pid is unusable")

    try:
        file_mode = stat.S_IMODE(os.stat(path).st_mode)
        folder_mode = stat.S_IMODE(os.stat(os.path.dirname(os.path.abspath(path))).st_mode)
    except OSError as error:
        results.add(FAIL, "PR-019", "descriptor-file-mode", "could not be read (%s)" % type(error).__name__)
    else:
        results.add(PASS if file_mode == 0o600 else FAIL, "PR-019", "descriptor-file-mode", "mode %04o" % file_mode)
        results.add(PASS if folder_mode == 0o700 else FAIL, "PR-019", "descriptor-folder-mode", "mode %04o" % folder_mode)

    if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
        results.add(*pid_result(pid))
    else:
        results.add(SKIP, "PR-020", "descriptor-pid", "pid is unusable")

    protocol = descriptor.get("protocol")
    if protocol == PROTOCOL:
        results.add(PASS, "PR-028", "descriptor-protocol", PROTOCOL)
    else:
        results.add(FAIL, "PR-028", "descriptor-protocol", "expected %s, found %s" % (PROTOCOL, printable(protocol)))
    return descriptor


def pid_result(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return FAIL, "PR-020", "descriptor-pid", "no process has the pid the descriptor names"
    except PermissionError:
        pass
    except OSError as error:
        return SKIP, "PR-020", "descriptor-pid", "could not ask the system (%s)" % type(error).__name__
    return PASS, "PR-020", "descriptor-pid", "the process is running"


# ------------------------------------------------------------- the answer

def walk(root):
    """Every element with its parent and its place, parents first.

    Yields (element, parent, label). A label is the element's id when the
    id has the right form, and otherwise its position in the tree, so that
    nothing else of the element is ever printed.
    """
    stack = [(root, None, "root")]
    while stack:
        element, parent, place = stack.pop()
        yield element, parent, place
        if isinstance(element, dict) and isinstance(element.get("children"), list):
            children = element["children"]
            for index in range(len(children) - 1, -1, -1):
                stack.append((children[index], element, "%s/%d" % (place, index)))


def label(element, place):
    if isinstance(element, dict) and isinstance(element.get("id"), str) and ID_FORM.match(element["id"]):
        return "element '%s'" % element["id"]
    return "the element at %s" % place


def check_tree(root):
    """Checks a tree against section 5 and schema/current-0.2.3.json.

    Returns a dict from check name to a list of problems, each naming
    elements by id or position only.
    """
    found = {name: [] for name in (
        "element-fields", "id-form", "ids-unique", "roles", "states-true-only",
        "focus-path", "hovered-single", "content-blocks",
    )}
    seen_ids = {}
    hovered = []
    count = 0

    for element, parent, place in walk(root):
        count += 1
        name = label(element, place)
        if not isinstance(element, dict):
            found["element-fields"].append("%s is not an object" % name)
            continue

        # Required fields and the types of the optional ones (5.1).
        identifier = element.get("id")
        if "id" not in element:
            found["element-fields"].append("%s has no id" % name)
        elif not isinstance(identifier, str):
            found["element-fields"].append("%s has an id that is not a string" % name)
        elif not ID_FORM.match(identifier):
            found["id-form"].append("%s has an id that is not 1 to 128 letters, digits, hyphens and underscores" % name)
        else:
            seen_ids[identifier] = seen_ids.get(identifier, 0) + 1
        role = element.get("role")
        if "role" not in element:
            found["element-fields"].append("%s has no role" % name)
        elif not isinstance(role, str):
            found["element-fields"].append("%s has a role that is not a string" % name)
        for field in ("subrole", "url"):
            if field in element and not (isinstance(element[field], str) and element[field]):
                found["element-fields"].append("%s has a %s that is not a non-empty string" % (name, field))
        if "title" in element and not isinstance(element["title"], str):
            found["element-fields"].append("%s has a title that is not a string" % name)
        if "visible" in element and not isinstance(element["visible"], bool):
            found["element-fields"].append("%s has a visible that is not true or false" % name)
        if "children" in element:
            if not isinstance(element["children"], list):
                found["element-fields"].append("%s has children that are not a list" % name)
            elif not element["children"]:
                found["element-fields"].append("%s sends an empty children list" % name)
        if "attributes" in element:
            attributes = element["attributes"]
            if not isinstance(attributes, dict):
                found["element-fields"].append("%s has attributes that are not an object" % name)
            else:
                if "author" in attributes and not isinstance(attributes["author"], str):
                    found["element-fields"].append("%s has an author attribute that is not a string" % name)
                related = attributes.get("related")
                if "related" in attributes and not (
                        isinstance(related, list) and all(isinstance(entry, dict) for entry in related)):
                    found["element-fields"].append("%s has a related attribute that is not a list of objects" % name)

        # Roles (5.2).
        if isinstance(role, str):
            if role not in ROLES:
                found["roles"].append("%s has role %s, which is not one of the thirteen" % (name, printable(role)))
            elif parent is None and role != "Application":
                found["roles"].append("the root has role '%s', not 'Application'" % role)
            elif parent is not None and role == "Application":
                found["roles"].append("%s is an Application below the root" % name)

        # States (5.3).
        for state in ("selected", "focused", "hovered"):
            if state in element and element[state] is not True:
                found["states-true-only"].append("%s sends %s with a value other than true" % (name, state))
        if element.get("hovered") is True:
            hovered.append(name)
        if isinstance(element.get("children"), list):
            focused_children = [
                child for child in element["children"]
                if isinstance(child, dict) and child.get("focused") is True
            ]
            if len(focused_children) > 1:
                found["focus-path"].append("%s has %d focused children" % (name, len(focused_children)))
        if element.get("focused") is True and parent is not None and parent is not root \
                and parent.get("focused") is not True:
            found["focus-path"].append("%s is focused and its parent, below the root, is not" % name)

        # Content (5.5).
        if "content" in element:
            content = element["content"]
            if not isinstance(content, list):
                found["element-fields"].append("%s has content that is not a list" % name)
            else:
                for index, block in enumerate(content):
                    problem = block_problem(block)
                    if problem:
                        found["content-blocks"].append("%s, content block %d: %s" % (name, index, problem))

    for identifier in sorted(seen_ids):
        if seen_ids[identifier] > 1:
            found["ids-unique"].append("id '%s' is used %d times" % (identifier, seen_ids[identifier]))
    if len(hovered) > 1:
        found["hovered-single"].append("%d elements are hovered: %s" % (len(hovered), ", ".join(hovered[:6])))
    return found, count


def block_problem(block):
    """What is wrong with a content block, or None. Only what MCP requires."""
    if not isinstance(block, dict):
        return "not an object"
    kind = block.get("type")
    if "type" not in block:
        return "no type"
    if not isinstance(kind, str) or kind not in BLOCK_FIELDS:
        return "type %s is not one of MCP's five" % printable(kind)
    missing = [field for field in BLOCK_FIELDS[kind] if field not in block]
    if missing:
        return "a %s block without %s" % (kind, " and ".join(missing))
    return None


def rect_ok(rect):
    return isinstance(rect, dict) and all(is_number(rect.get(side)) for side in ("x", "y", "w", "h"))


def location_problems(location, asked):
    """What is wrong with a location (section 6), as a list."""
    if not isinstance(location, dict):
        return ["the location is not an object"]
    problems = []
    if location.get("id") != asked:
        problems.append("its id is not the id asked about")
    state = location.get("state")
    if state not in LOCATION_STATES:
        problems.append("its state is %s, not visible, offscreen or gone" % printable(state))
    rects = location.get("rects")
    if "rects" in location:
        if not isinstance(rects, list) or not all(rect_ok(rect) for rect in rects):
            problems.append("rects is not a list of {x, y, w, h} numbers")
    if state == "visible" and not (isinstance(rects, list) and rects):
        problems.append("it is visible and has no rectangle")
    if "window" in location and not is_number(location["window"]):
        problems.append("window is not a number")
    if "avoid" in location and not rect_ok(location["avoid"]):
        problems.append("avoid is not a rectangle")
    if "edge" in location and location["edge"] not in EDGES:
        problems.append("edge is not left, right, top or bottom")
    return problems


def read_document(response, uri):
    """The JSON document in a resources/read result, and what is wrong.

    Returns (document or None, problems).
    """
    result = response.result()
    if response.status != 200 or result is None:
        return None, [response.describe()]
    problems = []
    contents = result.get("contents")
    if not isinstance(contents, list) or len(contents) != 1 or not isinstance(contents[0], dict):
        size = len(contents) if isinstance(contents, list) else 0
        return None, ["contents holds %d entries, not exactly one" % size]
    entry = contents[0]
    if entry.get("uri") != uri:
        problems.append("the entry's uri is not the address that was read")
    if entry.get("mimeType") != "application/json":
        problems.append("the entry's mimeType is not application/json")
    document = None
    if not isinstance(entry.get("text"), str):
        problems.append("the entry has no text")
    else:
        try:
            document = json.loads(entry["text"])
        except ValueError:
            problems.append("the entry's text is not a JSON document")
    return document, problems


# -------------------------------------------------------------- the checks

def check_refusals(client, results):
    """Section 7.4, the cases that need no knowledge of the provider's answer."""
    response = client.rpc("resources/list", token=None)
    results.add(PASS if response.status == 401 else FAIL, "PR-032", "token-missing",
                "no Authorization header: " + response.describe())

    wrong = [
        ("a different token", secrets.token_urlsafe(24)),
        ("the token with a character added", client.token + "x"),
        ("an empty token", ""),
    ]
    problems = []
    for what, token in wrong:
        response = client.rpc("resources/list", token=token)
        if response.status != 401:
            problems.append("%s: %s" % (what, response.describe()))
    results.judge("PR-032", "token-wrong", problems, "401 for three wrong tokens")

    origin = {"Origin": "http://localhost:3000"}
    response = client.rpc("resources/list", extra_headers=origin)
    problems = []
    if response.status != 403:
        problems.append(response.describe())
    elif response.body:
        problems.append("HTTP 403 with a body, where 7.4 asks for none")
    results.judge("PR-033", "origin-refused", problems, "403 with the right token and an Origin header")

    response = client.rpc("resources/list", token=None, extra_headers={"Origin": "null"})
    results.add(PASS if response.status == 403 else FAIL, "PR-033", "origin-before-token",
                "an Origin header and no token: " + response.describe())

    preflight = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization, content-type",
    }
    response = client.send("OPTIONS", preflight)
    results.add(PASS if response.status == 403 else FAIL, "PR-033", "origin-options",
                "a cross-origin preflight: " + response.describe())

    problems = []
    authorized = {"Authorization": "Bearer " + client.token}
    for http_method in ("GET", "PUT", "DELETE", "OPTIONS"):
        response = client.send(http_method, authorized)
        if response.status != 405:
            problems.append("%s: %s" % (http_method, response.describe()))
    results.judge("PR-065", "method-not-post", problems, "405 for GET, PUT, DELETE and OPTIONS")

    # A body of one gibibyte is declared and never sent. A provider with
    # any limit refuses on the declared length.
    headers = {"Authorization": "Bearer " + client.token, "Content-Type": "application/json",
               "MCP-Protocol-Version": MCP_VERSION, "Mcp-Method": "resources/list"}
    response = client.send("POST", headers, declared_length=1 << 30, timeout=min(client.timeout, 2.0))
    if response.status == 413:
        results.add(PASS, "PR-065", "oversized-request", "413 for a declared body of 1 GiB")
    elif response.failure:
        results.add(WARN, "PR-065", "oversized-request",
                    "a declared body of 1 GiB got %s; the provider may refuse only once the bytes arrive, which this check does not send" % response.describe())
    else:
        results.add(FAIL, "PR-065", "oversized-request", "a declared body of 1 GiB: " + response.describe())

    problems = []
    response = client.rpc("resources/list", raw_body=b"{not json")
    if not response.refused_with(400, -32700):
        problems.append("a body that is not JSON: %s, expected HTTP 400, error -32700" % response.describe())
    response = client.rpc("resources/list", raw_body=b'{"jsonrpc":"2.0","id":1}')
    if not response.refused_with(400, -32600):
        problems.append("a body with no method: %s, expected HTTP 400, error -32600" % response.describe())
    results.judge("PR-026", "malformed-body", problems, "400 with -32700 and -32600")

    response = client.rpc("resources/list", version=None, header_version=MCP_VERSION)
    results.add(PASS if response.refused_with(400, -32602) else FAIL, "PR-064", "meta-version-required",
                "no protocolVersion in _meta: " + response.describe())
    response = client.rpc("resources/list", capabilities=None)
    results.add(PASS if response.refused_with(400, -32602) else FAIL, "PR-064", "meta-capabilities-required",
                "no clientCapabilities in _meta: " + response.describe())

    read = {"uri": CURRENT_URI}
    cases = [
        ("MCP-Protocol-Version missing", client.rpc("resources/list", header_version=None)),
        ("MCP-Protocol-Version disagrees", client.rpc("resources/list", header_version=LEGACY_VERSION)),
        ("Mcp-Method missing", client.rpc("resources/list", method_header=None)),
        ("Mcp-Method disagrees", client.rpc("resources/list", method_header="resources/read")),
        ("Mcp-Name missing", client.rpc("resources/read", read, name_header=None)),
        ("Mcp-Name disagrees", client.rpc("resources/read", read, name_header=LOCATION_PREFIX + "x")),
    ]
    problems = ["%s: %s" % (what, response.describe()) for what, response in cases
                if not response.refused_with(400, -32020)]
    results.judge("PR-065", "header-mismatch", problems, "400 with -32020 in six cases")

    response = client.rpc("tools/list")
    results.add(PASS if response.refused_with(404, -32601) else FAIL, "PR-026", "unknown-method",
                "tools/list: " + response.describe())
    response = client.rpc("resources/list", version="1900-01-01")
    results.add(PASS if response.refused_with(400, -32022) else FAIL, "PR-026", "unsupported-version",
                "MCP 1900-01-01: " + response.describe())


DISPLAY_LIMIT = 80


def display_problems(display):
    """Section 4.3. Names the fields and never quotes them: they are the user's."""
    if not isinstance(display, dict):
        return ["display is not an object"]
    problems = []
    for name in ("title", "detail"):
        if name not in display:
            continue
        line = display[name]
        if not isinstance(line, str):
            problems.append("display.%s is not a string" % name)
        elif "\n" in line or "\r" in line:
            problems.append("display.%s holds a line break" % name)
        elif len(line) > DISPLAY_LIMIT:
            problems.append("display.%s is %d characters, over %d" % (name, len(line), DISPLAY_LIMIT))
    return problems


def complete(result):
    return [] if result.get("resultType") == "complete" else ["resultType is not 'complete'"]


def check_reads(client, results, expected_instance, slow):
    """Sections 7.2 and 7.3, then the answer itself.

    Returns (root, locate offered, watch declared). The last is None when
    server/discover was not answered.
    """
    response = client.rpc("server/discover")
    result = response.result()
    watch = None
    if response.status != 200 or result is None:
        results.add(FAIL, "PR-026", "discover", response.describe())
        results.add(SKIP, "PR-098", "discover-extension", "server/discover was not answered")
    else:
        problems = complete(result)
        versions = result.get("supportedVersions")
        if not (isinstance(versions, list) and MCP_VERSION in versions):
            problems.append("supportedVersions does not name %s" % MCP_VERSION)
        capabilities = result.get("capabilities") if isinstance(result.get("capabilities"), dict) else {}
        if not isinstance(capabilities.get("resources"), dict):
            problems.append("capabilities has no resources object")
        else:
            watch = capabilities["resources"].get("subscribe") is True
        results.judge("PR-026", "discover", problems, "names MCP %s and offers resources" % MCP_VERSION)
        results.add(*extension_result(capabilities.get("extensions"), "PR-098", "discover-extension", "capabilities.extensions"))

    response = client.rpc("resources/list")
    result = response.result()
    if response.status != 200 or result is None:
        results.add(FAIL, "PR-024", "resources-list", response.describe())
    else:
        problems = complete(result)
        resources = result.get("resources") if isinstance(result.get("resources"), list) else []
        if not any(isinstance(entry, dict) and entry.get("uri") == CURRENT_URI for entry in resources):
            problems.append("%s is not among the %d resources listed" % (CURRENT_URI, len(resources)))
        results.judge("PR-024", "resources-list", problems, "lists %s" % CURRENT_URI)

    response = client.rpc("resources/templates/list")
    result = response.result()
    locate = False
    if response.status != 200 or result is None:
        results.add(FAIL, "PR-024", "templates-list", response.describe())
    else:
        problems = complete(result)
        templates = result.get("resourceTemplates")
        if not isinstance(templates, list):
            problems.append("resourceTemplates is not a list")
            templates = []
        locate = any(isinstance(entry, dict) and entry.get("uriTemplate") == LOCATION_TEMPLATE for entry in templates)
        offered = "offers %s" % LOCATION_TEMPLATE if locate else "answered; the location template is not offered, which is allowed"
        results.judge("PR-024", "templates-list", problems, offered)

    response = client.rpc("resources/read", {"uri": CURRENT_URI})
    answer, problems = read_document(response, CURRENT_URI)
    if response.result() is not None:
        problems += complete(response.result())
    results.judge("PR-024", "read-current", problems, "one application/json entry")

    tree_checks = [
        ("PR-048", "element-fields"), ("PR-059", "id-form"), ("PR-059", "ids-unique"), ("PR-049", "roles"),
        ("PR-050", "states-true-only"), ("PR-051", "focus-path"), ("PR-053", "hovered-single"),
        ("PR-005", "content-blocks"),
    ]
    if not isinstance(answer, dict):
        reason = "no answer to check" if answer is None else "the answer is not an object"
        for requirement, name in [("PR-072", "current-fields"), ("PR-098", "current-protocol"),
                                  ("PR-040", "current-instance"), ("PR-074", "current-display")] + tree_checks + [("PR-004", "current-time")]:
            results.add(SKIP if answer is None else FAIL, requirement, name, reason)
        return None, locate, watch

    keys = set(answer)
    problems = ["'%s' is missing" % name for name in ("protocol", "instance", "root") if name not in keys]
    extra = len(keys - {"protocol", "instance", "root", "display"})
    if extra:
        problems.append("%d extra field%s beside protocol, instance, root and display" % (extra, "" if extra == 1 else "s"))
    results.judge("PR-072", "current-fields", problems, "protocol, instance and root%s, and nothing else"
                  % (" with display" if "display" in keys else ""))

    if "display" in answer:
        results.judge("PR-074", "current-display", display_problems(answer["display"]),
                      "an object whose strings are each one line of at most %d characters" % DISPLAY_LIMIT)
    else:
        results.add(PASS, "PR-074", "current-display", "no display is sent, which is allowed")

    if answer.get("protocol") == PROTOCOL:
        results.add(PASS, "PR-098", "current-protocol", PROTOCOL)
    else:
        results.add(FAIL, "PR-098", "current-protocol", "expected %s, found %s" % (PROTOCOL, printable(answer.get("protocol"))))

    instance = answer.get("instance")
    if not (isinstance(instance, str) and instance):
        results.add(FAIL, "PR-040", "current-instance", "instance is not a non-empty string")
    elif expected_instance is None:
        results.add(SKIP, "PR-040", "current-instance", "no instance was given to compare with")
    elif instance == expected_instance:
        results.add(PASS, "PR-040", "current-instance", "equals the descriptor's")
    else:
        results.add(FAIL, "PR-040", "current-instance", "differs from the descriptor's")

    root = answer.get("root")
    if "root" not in answer:
        for requirement, name in tree_checks:
            results.add(SKIP, requirement, name, "the answer has no root")
        root = None
    else:
        found, count = check_tree(root)
        for requirement, name in tree_checks:
            results.judge(requirement, name, found[name], "%d element%s" % (count, "" if count == 1 else "s"))

    milliseconds = int(response.seconds * 1000)
    if response.seconds > slow:
        results.add(WARN, "PR-004", "current-time", "answered in %d ms, over the %d ms this run allows" % (milliseconds, int(slow * 1000)))
    else:
        results.add(PASS, "PR-004", "current-time", "answered in %d ms" % milliseconds)
    return (root if isinstance(root, dict) else None), locate, watch


def extension_result(holder, requirement, name, where):
    settings = holder.get(EXTENSION) if isinstance(holder, dict) else None
    if not isinstance(settings, dict):
        return FAIL, requirement, name, "%s does not declare %s" % (where, EXTENSION)
    if settings.get("version") != PROTOCOL:
        return FAIL, requirement, name, "declares version %s, expected %s" % (printable(settings.get("version")), PROTOCOL)
    return PASS, requirement, name, "%s version %s" % (EXTENSION, PROTOCOL)


def check_locate(client, results, root, offered, limit):
    """Sections 4.2 and 6."""
    if not offered:
        results.add(SKIP, "PR-011", "locate-issued", "the provider does not offer locate")
        results.add(SKIP, "PR-060", "locate-never-issued", "the provider does not offer locate")
        return

    ids, marked = [], []
    if root is not None:
        for element, _parent, _place in walk(root):
            if isinstance(element, dict) and isinstance(element.get("id"), str) and ID_FORM.match(element["id"]):
                pointed = any(element.get(state) is True for state in ("selected", "focused", "hovered"))
                (marked if pointed else ids).append(element["id"])
    # What the user is pointing at is asked about first.
    candidates = list(dict.fromkeys(marked + ids))
    if not candidates:
        results.add(SKIP, "PR-011", "locate-issued", "no usable id in the answer to ask about")
    else:
        tallies = {"visible": 0, "offscreen": 0, "gone": 0, "cannot place": 0}
        problems = []
        for identifier in candidates[:limit]:
            uri = LOCATION_PREFIX + identifier
            response = client.rpc("resources/read", {"uri": uri})
            if response.error_code() == -32602:
                tallies["cannot place"] += 1
                continue
            location, found = read_document(response, uri)
            if location is not None:
                found += location_problems(location, identifier)
            if found:
                problems.append("id '%s': %s" % (identifier, ", ".join(found)))
            elif location.get("state") in tallies:
                tallies[location["state"]] += 1
        asked = min(len(candidates), limit)
        detail = "asked about %d of %d ids: %s" % (asked, len(candidates), ", ".join(
            "%d %s" % (tallies[state], state) for state in ("visible", "offscreen", "gone", "cannot place")))
        results.judge("PR-011", "locate-issued", problems, detail)

    known = set(candidates)
    never = "never-issued-" + secrets.token_hex(6)
    while never in known:
        never = "never-issued-" + secrets.token_hex(6)
    response = client.rpc("resources/read", {"uri": LOCATION_PREFIX + never})
    results.add(PASS if response.error_code() == -32602 else FAIL, "PR-060", "locate-never-issued",
                "an id never issued: " + response.describe())


WATCH_CHECKS = [
    ("PR-080", "watch-served"), ("PR-080", "watch-acknowledged"), ("PR-080", "watch-filter-narrowed"),
    ("PR-082", "watch-filter-refused"), ("PR-087", "watch-token"), ("PR-087", "watch-origin"),
    ("PR-082", "watch-notices"), ("PR-083", "watch-coalesced"), ("PR-085", "watch-keepalive"),
]


def describe_watch(watch):
    """What a watch request got, in status codes only."""
    return "HTTP 200, an event stream" if watch.streaming else watch.response.describe()


def skip_watch(results, reason, done=()):
    for requirement, name in WATCH_CHECKS:
        if name not in done:
            results.add(SKIP, requirement, name, reason)


def check_watch(client, results, declared, hold, keepalive=KEEPALIVE):
    """Sections 4.4 and 7.7: the watch on current (RFC-0006).

    One watch is opened and held for `hold` seconds while the rest is
    asked. Only what arrives is judged: a real app sends a notice only if
    the user changes something in that time.
    """
    if declared is None:
        skip_watch(results, "server/discover was not answered")
        return
    watch = client.watch()
    try:
        if not declared:
            if watch.streaming:
                results.add(FAIL, "PR-081", "watch-not-offered",
                            "resources.subscribe is not declared and %s opens an event stream" % LISTEN)
            elif watch.response.refused_with(404, -32601):
                results.add(PASS, "PR-081", "watch-not-offered",
                            "no subscribe is declared; %s: %s" % (LISTEN, describe_watch(watch)))
            else:
                results.add(FAIL, "PR-081", "watch-not-offered",
                            "no subscribe is declared; %s: %s, expected HTTP 404, error -32601" % (LISTEN, describe_watch(watch)))
            skip_watch(results, "the provider does not offer watch")
            return

        if watch.streaming:
            results.add(PASS, "PR-080", "watch-served", "resources.subscribe is declared and %s opens an event stream" % LISTEN)
            first = watch.first_message(client.timeout)
            results.judge("PR-080", "watch-acknowledged", acknowledgment_problems(first, watch.request_id),
                          "the first message, naming %s alone and the request's id" % CURRENT_URI)
            check_watch_filters(client, results)
        else:
            results.add(FAIL, "PR-080", "watch-served",
                        "resources.subscribe is declared; %s: %s" % (LISTEN, describe_watch(watch)))
        check_watch_refusals(client, results)
        if not watch.streaming:
            skip_watch(results, "the watch did not open", done=("watch-served", "watch-token", "watch-origin"))
            return

        watch.collect(hold)
        ended = watch.ended  # Read before the time, so that an end is never dated late.
        until = watch.ended_at if ended else time.monotonic()
        events = watch.snapshot()
        problems, notices = stream_problems(events, watch.request_id)
        if notices:
            passed = "%s, each for %s with the subscription id and nothing else" % (several(notices, "notice"), CURRENT_URI)
        else:
            passed = "no change happened while watching, so no notice was seen"
        results.judge("PR-082", "watch-notices", problems, passed)
        results.add(*coalescing_result([event.at for event in events if event.method == UPDATED]))
        results.add(*keepalive_result(watch, events, until, ended, hold, keepalive))
    finally:
        watch.close()


def check_watch_filters(client, results):
    """Section 7.7: what a provider does with a filter that asks for more, or for something else."""
    wide = {"resourceSubscriptions": [CURRENT_URI, LOCATION_PREFIX + "x"],
            "toolsListChanged": True, "promptsListChanged": True, "resourcesListChanged": True}
    other = client.watch(wide)
    try:
        if other.streaming:
            problems = acknowledgment_problems(other.first_message(client.timeout), other.request_id)
        else:
            problems = [describe_watch(other)]
    finally:
        other.close()
    results.judge("PR-080", "watch-filter-narrowed", ["asked for a location and list changes too: " + summarize(problems)] if problems else [],
                  "a filter that asks for a location and list changes too is acknowledged for %s alone" % CURRENT_URI)

    cases = [
        ("a filter that names a location only", {"resourceSubscriptions": [LOCATION_PREFIX + "x"]}),
        ("a filter that asks for list changes only", {"resourcesListChanged": True}),
    ]
    problems = []
    for what, notifications in cases:
        other = client.watch(notifications)
        other.close()
        if other.streaming or not other.response.refused_with(400, -32602):
            problems.append("%s: %s" % (what, describe_watch(other)))
    results.judge("PR-082", "watch-filter-refused", problems,
                  "400 with -32602 for two filters that do not name %s" % CURRENT_URI)


def check_watch_refusals(client, results):
    """Section 7.1: the token and Origin rules, before any stream opens."""
    problems = []
    for what, token in (("no Authorization header", None), ("a different token", secrets.token_urlsafe(24))):
        other = client.watch(token=token)
        other.close()
        if other.response.status != 401:
            problems.append("%s: %s" % (what, describe_watch(other)))
    results.judge("PR-087", "watch-token", problems, "401 and no stream, with no token and with a wrong one")

    other = client.watch(extra_headers={"Origin": "http://localhost:3000"})
    other.close()
    results.judge("PR-087", "watch-origin", [] if other.response.status == 403 else [describe_watch(other)],
                  "403 and no stream, with the right token and an Origin header")


def keepalive_result(watch, events, until, ended, hold, keepalive=KEEPALIVE):
    """PR-085: on a held watch, something arrives at least every `keepalive` seconds."""
    again = "pass --watch-hold %d to judge it" % (KEEPALIVE + 5)
    if hold <= 0:
        return SKIP, "PR-085", "watch-keepalive", "the watch was not held open; " + again
    start = events[0].at if events else watch.opened_at
    times = [start] + [event.at for event in events if event.at > start] + [until]
    held = until - start
    if held < keepalive + KEEPALIVE_TOLERANCE:
        if ended:
            return SKIP, "PR-085", "watch-keepalive", "the provider ended the watch after %.1f s, too soon to judge" % held
        return SKIP, "PR-085", "watch-keepalive", "held for %.1f s, too short to judge a comment line every %g s; %s" % (held, keepalive, again)
    silence = max(later - earlier for earlier, later in zip(times, times[1:]))
    if silence > keepalive + KEEPALIVE_TOLERANCE:
        return FAIL, "PR-085", "watch-keepalive", "nothing on the stream for %.1f s; a comment line is due at least every %g s" % (silence, keepalive)
    comments = sum(1 for event in events if event.kind == "comment")
    notices = sum(1 for event in events if event.method == UPDATED)
    return PASS, "PR-085", "watch-keepalive", "%s and %s in %.1f s; the longest silence %.1f s" % (
        several(comments, "comment line"), several(notices, "notice"), held, silence)


# ------------------------------------------- checks that need the app driven

def drive_changes(watch, change, results, burst=None, wait=1.0, window=COALESCE + 0.2):
    """PR-084's second half and PR-083, for a test that can change the app.

    `change()` must make one real change to the answer to current, such
    as selecting something else, and return. `burst()`, if given, must
    make several at once. Nothing else may change the app meanwhile. The
    watch must be open and acknowledged.

    Adds `watch-change-noticed` (a change is followed by a notice),
    `watch-trailing-notice` (a second change, made inside the 250 ms after
    that notice, still gets its own: delayed, never dropped) and, with
    `burst`, `watch-burst-coalesced` (no two notices closer than 250 ms).
    """
    began = time.monotonic()
    change()
    first = watch.wait_notice(began, wait)
    if first is None:
        results.add(FAIL, "PR-084", "watch-change-noticed", "no notice within %g s of a change" % wait)
        results.add(SKIP, "PR-083", "watch-trailing-notice", "the first change was not noticed")
        if burst is not None:
            results.add(SKIP, "PR-083", "watch-burst-coalesced", "the first change was not noticed")
        return
    results.add(PASS, "PR-084", "watch-change-noticed", "a notice %d ms after a change" % int((first - began) * 1000))

    again = time.monotonic()
    change()
    last = watch.wait_notice(again, wait)
    after = int((again - first) * 1000)
    if last is None:
        results.add(FAIL, "PR-083", "watch-trailing-notice",
                    "a change made %d ms after a notice got no notice of its own within %g s" % (after, wait))
    else:
        results.add(PASS, "PR-083", "watch-trailing-notice",
                    "a change made %d ms after a notice got its own %d ms later" % (after, int((last - again) * 1000)))

    if burst is not None:
        burst()
        watch.collect(window)
        results.add(*coalescing_result(watch.notice_times(began), "watch-burst-coalesced"))


def drive_hover(watch, hover, results, settle=COALESCE + 0.1, quiet=0.6):
    """PR-084's first half: `hover()` must change which element is hovered
    and nothing else. Adds `watch-hover-silent`: no notice follows in `quiet`
    seconds. `settle` lets a notice still owed for an earlier change arrive first.
    """
    watch.collect(settle)
    began = time.monotonic()
    hover()
    watch.collect(quiet)
    notices = len(watch.notice_times(began))
    if notices:
        results.add(FAIL, "PR-084", "watch-hover-silent", "%s within %g s of a change in hovered alone" % (several(notices, "notice"), quiet))
    else:
        results.add(PASS, "PR-084", "watch-hover-silent", "no notice in %g s after a change in hovered alone" % quiet)


def drive_stop(watch, stop, results, wait=2.0):
    """PR-086: `stop()` must quit the provider or turn it off. Adds
    `watch-ends-at-stop`: the stream ends within `wait` seconds.
    """
    stop()
    if not watch.wait_end(wait):
        results.add(FAIL, "PR-086", "watch-ends-at-stop", "the stream was still open %g s after the provider stopped" % wait)
    elif watch.completed:
        results.add(PASS, "PR-086", "watch-ends-at-stop", "the stream ended with a completion result")
    else:
        results.add(PASS, "PR-086", "watch-ends-at-stop", "the stream was closed, with no completion result")


def check_older_clients(client, results):
    """Section 7.1's ping and section 7.6. Both are things a provider should do."""
    response = client.rpc("ping")
    if response.status == 200 and response.result() is not None:
        results.add(PASS, "PR-026", "ping", "answered")
    else:
        results.add(WARN, "PR-026", "ping", "not answered (%s); a provider should answer ping" % response.describe())

    response = client.legacy("initialize", {
        "protocolVersion": LEGACY_VERSION, "capabilities": {},
        "clientInfo": {"name": "ambient-context-conformance", "version": PROTOCOL},
    }, header=None)
    result = response.result()
    if response.status != 200 or result is None:
        results.add(WARN, "PR-026", "legacy-initialize",
                    "not answered (%s); a provider should serve older clients" % response.describe())
        results.add(SKIP, "PR-098", "legacy-extension", "the initialize handshake is not offered")
        results.add(SKIP, "PR-025", "legacy-read", "the initialize handshake is not offered")
        return
    if isinstance(result.get("protocolVersion"), str) and result["protocolVersion"]:
        results.add(PASS, "PR-026", "legacy-initialize", "answered with MCP %s" % printable(result["protocolVersion"]))
    else:
        results.add(FAIL, "PR-026", "legacy-initialize", "the result names no protocolVersion")
    capabilities = result.get("capabilities") if isinstance(result.get("capabilities"), dict) else {}
    results.add(*extension_result(capabilities.get("experimental"), "PR-098", "legacy-extension", "capabilities.experimental"))

    # With no knowledge of this protocol: list, then read, with nothing in
    # _meta. Only that both are answered; the answer itself is judged above.
    problems = []
    listed = client.legacy("resources/list")
    result = listed.result()
    if listed.status != 200 or result is None or not isinstance(result.get("resources"), list):
        problems.append("resources/list: %s" % listed.describe())
    for header in (LEGACY_VERSION, None):
        read = client.legacy("resources/read", {"uri": CURRENT_URI}, header=header)
        result = read.result()
        how = "with an older version header" if header else "with no version at all"
        if read.status != 200 or result is None or not (isinstance(result.get("contents"), list) and result["contents"]):
            problems.append("resources/read %s: %s" % (how, read.describe()))
    results.judge("PR-025", "legacy-read", problems, "an older client lists resources and reads %s" % CURRENT_URI)


def check_cors(client, results):
    """No response from the path may carry an Access-Control-Allow-* header."""
    answered = [response for response in client.seen if response.status is not None]
    names = sorted({name.lower() for response in answered for name, _value in response.headers
                    if name.lower().startswith("access-control-allow-")})
    carrying = sum(1 for response in answered
                   if any(name.lower().startswith("access-control-allow-") for name, _value in response.headers))
    if not answered:
        results.add(SKIP, "PR-063", "cors-headers", "no response to inspect")
    elif names:
        results.add(FAIL, "PR-063", "cors-headers", "%d of %d responses carry %s" % (carrying, len(answered), ", ".join(names)))
    else:
        results.add(PASS, "PR-063", "cors-headers", "none on %d responses" % len(answered))


# -------------------------------------------------------------------- run

def run(descriptor_path=None, endpoint=None, token=None, instance=None, pid=None,
        timeout=5.0, slow=1.0, locate_limit=25, watch_hold=2.0, watch_keepalive=KEEPALIVE):
    """Runs every check and returns the Results.

    `watch_hold` is how long the watch is held open, in seconds. The
    keep-alive rule is judged only when that is longer than
    `watch_keepalive`, which is the specification's 15 seconds unless a
    test of this script shortens it.
    """
    results = Results()
    answers_for = False
    if descriptor_path is not None:
        descriptor = check_descriptor_file(descriptor_path, results)
        if descriptor is None:
            return results
        endpoint, token, instance = descriptor.get("endpoint"), descriptor.get("token"), descriptor.get("instance")
        answers_for = descriptor.get("for") is not None
        if not isinstance(instance, str):
            instance = None
    elif pid is not None:
        results.add(*pid_result(pid))

    host, port, path, address_problems, path_problems = parse_endpoint(endpoint)
    results.judge("PR-031", "endpoint-address", address_problems, "the descriptor names 127.0.0.1" if descriptor_path else "the endpoint names 127.0.0.1")
    if host is not None:
        results.judge("PR-062", "endpoint-path", path_problems, "begins with / and has no query or fragment")

    # The token is sent to this machine only, whatever the descriptor says.
    if host not in LOOPBACK_NAMES or port is None or not path or not path.startswith("/") \
            or not isinstance(token, str) or not token:
        results.add(SKIP, "PR-062", "endpoint-answers", "no request was sent: the endpoint or token is unusable, or the address is not this machine")
        return results
    if "?" in endpoint:
        path += "?" + urlsplit(endpoint).query

    client = Client(host, port, path, token, timeout)
    response = client.rpc("resources/list")
    if response.failure:
        results.add(FAIL, "PR-062", "endpoint-answers", response.describe())
        return results
    results.add(PASS, "PR-062", "endpoint-answers", "a POST is answered")

    check_refusals(client, results)
    root, locate, watch = check_reads(client, results, instance, slow)
    if answers_for:
        results.add(*via_result(root))
    check_locate(client, results, root, locate, locate_limit)
    check_watch(client, results, watch, watch_hold, watch_keepalive)
    check_older_clients(client, results)
    check_cors(client, results)
    return results


def render(results):
    width = max([len(item["name"]) for item in results.items] + [1])
    lines = ["%-4s  %-6s  %-*s  %s" % (item["status"], item["requirement"], width, item["name"], item["detail"])
             for item in results.items]
    lines.append("%d passed, %d failed, %d warned, %d skipped" % tuple(results.count(s) for s in (PASS, FAIL, WARN, SKIP)))
    return "\n".join(line.rstrip() for line in lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check a running Ambient Context Protocol %s provider from outside." % PROTOCOL)
    parser.add_argument("descriptor", nargs="?", help="path to the provider's descriptor file")
    parser.add_argument("--endpoint", help="the provider's endpoint, when no descriptor is given")
    parser.add_argument("--token", help="the bearer token, when no descriptor is given")
    parser.add_argument("--instance", help="the instance the answer must carry (with --endpoint)")
    parser.add_argument("--pid", type=int, help="the provider's process id (with --endpoint)")
    parser.add_argument("--json", action="store_true", help="print the results as JSON")
    parser.add_argument("--timeout", type=float, default=5.0, help="seconds to wait for each response (default 5)")
    parser.add_argument("--slow", type=float, default=1.0, help="seconds after which a current answer is warned about (default 1)")
    parser.add_argument("--locate-limit", type=int, default=25, help="how many ids to ask locate about (default 25)")
    parser.add_argument("--watch-hold", type=float, default=2.0, metavar="SECONDS",
                        help="seconds to hold a watch open and judge what arrives (default 2; 20 or more also judges the 15 s keep-alive)")
    arguments = parser.parse_args(argv)

    if arguments.descriptor and (arguments.endpoint or arguments.token):
        parser.error("give a descriptor file or --endpoint and --token, not both")
    if not arguments.descriptor and not (arguments.endpoint and arguments.token):
        parser.error("give a descriptor file, or both --endpoint and --token")

    results = run(
        descriptor_path=arguments.descriptor, endpoint=arguments.endpoint, token=arguments.token,
        instance=arguments.instance, pid=arguments.pid, timeout=arguments.timeout,
        slow=arguments.slow, locate_limit=max(arguments.locate_limit, 1), watch_hold=max(arguments.watch_hold, 0.0),
    )
    if arguments.json:
        print(json.dumps({
            "protocol": PROTOCOL,
            "summary": {status.lower(): results.count(status) for status in (PASS, FAIL, WARN, SKIP)},
            "results": results.items,
        }, indent=2))
    else:
        print(render(results))
    return 1 if results.failed else 0


if __name__ == "__main__":
    sys.exit(main())
