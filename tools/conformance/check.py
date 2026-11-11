#!/usr/bin/env python3
"""An outside check for an Ambient Context Protocol provider, version 0.2.0.

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

Python 3 standard library only.
"""
import argparse
import http.client
import json
import os
import re
import secrets
import socket
import stat
import sys
import time
from urllib.parse import urlsplit

PROTOCOL = "0.2.0"
MCP_VERSION = "2026-07-28"
LEGACY_VERSION = "2025-11-25"
EXTENSION = "io.github.ambientcontextprotocol/context"
CURRENT_URI = "ambient://current"
LOCATION_TEMPLATE = "ambient://location/{id}"
LOCATION_PREFIX = "ambient://location/"
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"

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

    if isinstance(app, dict) and isinstance(app.get("id"), str) and isinstance(pid, int):
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
    """Checks a tree against section 5 and schema/current-0.2.0.json.

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


def complete(result):
    return [] if result.get("resultType") == "complete" else ["resultType is not 'complete'"]


def check_reads(client, results, expected_instance, slow):
    """Sections 7.2 and 7.3, then the answer itself. Returns (root, locate offered)."""
    response = client.rpc("server/discover")
    result = response.result()
    if response.status != 200 or result is None:
        results.add(FAIL, "PR-026", "discover", response.describe())
        results.add(SKIP, "PR-066", "discover-extension", "server/discover was not answered")
    else:
        problems = complete(result)
        versions = result.get("supportedVersions")
        if not (isinstance(versions, list) and MCP_VERSION in versions):
            problems.append("supportedVersions does not name %s" % MCP_VERSION)
        capabilities = result.get("capabilities") if isinstance(result.get("capabilities"), dict) else {}
        if not isinstance(capabilities.get("resources"), dict):
            problems.append("capabilities has no resources object")
        results.judge("PR-026", "discover", problems, "names MCP %s and offers resources" % MCP_VERSION)
        results.add(*extension_result(capabilities.get("extensions"), "PR-066", "discover-extension", "capabilities.extensions"))

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
        for requirement, name in [("PR-047", "current-fields"), ("PR-066", "current-protocol"),
                                  ("PR-040", "current-instance")] + tree_checks + [("PR-004", "current-time")]:
            results.add(SKIP if answer is None else FAIL, requirement, name, reason)
        return None, locate

    keys = set(answer)
    problems = ["'%s' is missing" % name for name in ("protocol", "instance", "root") if name not in keys]
    extra = len(keys - {"protocol", "instance", "root"})
    if extra:
        problems.append("%d extra field%s beside protocol, instance and root" % (extra, "" if extra == 1 else "s"))
    results.judge("PR-047", "current-fields", problems, "exactly protocol, instance and root")

    if answer.get("protocol") == PROTOCOL:
        results.add(PASS, "PR-066", "current-protocol", PROTOCOL)
    else:
        results.add(FAIL, "PR-066", "current-protocol", "expected %s, found %s" % (PROTOCOL, printable(answer.get("protocol"))))

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
    return (root if isinstance(root, dict) else None), locate


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
        results.add(SKIP, "PR-066", "legacy-extension", "the initialize handshake is not offered")
        results.add(SKIP, "PR-025", "legacy-read", "the initialize handshake is not offered")
        return
    if isinstance(result.get("protocolVersion"), str) and result["protocolVersion"]:
        results.add(PASS, "PR-026", "legacy-initialize", "answered with MCP %s" % printable(result["protocolVersion"]))
    else:
        results.add(FAIL, "PR-026", "legacy-initialize", "the result names no protocolVersion")
    capabilities = result.get("capabilities") if isinstance(result.get("capabilities"), dict) else {}
    results.add(*extension_result(capabilities.get("experimental"), "PR-066", "legacy-extension", "capabilities.experimental"))

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
        timeout=5.0, slow=1.0, locate_limit=25):
    """Runs every check and returns the Results."""
    results = Results()
    if descriptor_path is not None:
        descriptor = check_descriptor_file(descriptor_path, results)
        if descriptor is None:
            return results
        endpoint, token, instance = descriptor.get("endpoint"), descriptor.get("token"), descriptor.get("instance")
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
    root, locate = check_reads(client, results, instance, slow)
    check_locate(client, results, root, locate, locate_limit)
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
    arguments = parser.parse_args(argv)

    if arguments.descriptor and (arguments.endpoint or arguments.token):
        parser.error("give a descriptor file or --endpoint and --token, not both")
    if not arguments.descriptor and not (arguments.endpoint and arguments.token):
        parser.error("give a descriptor file, or both --endpoint and --token")

    results = run(
        descriptor_path=arguments.descriptor, endpoint=arguments.endpoint, token=arguments.token,
        instance=arguments.instance, pid=arguments.pid, timeout=arguments.timeout,
        slow=arguments.slow, locate_limit=max(arguments.locate_limit, 1),
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
