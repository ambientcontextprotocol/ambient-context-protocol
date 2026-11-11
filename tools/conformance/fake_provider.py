#!/usr/bin/env python3
"""A fake Ambient Context Protocol provider, version 0.2.0.

Serves one fixed, valid tree on a loopback port, writes a descriptor into
the folder named by --directory and removes it on exit. It exists to test
a host, and to test the conformance check itself: each --fault breaks one
requirement the check can see.

    python3 tools/conformance/fake_provider.py --directory /tmp/acp/providers
    python3 tools/conformance/fake_provider.py --directory DIR --fault two-hovered
    python3 tools/conformance/fake_provider.py --list-faults

It never writes to the real descriptor folder: --directory is required and
a path inside ~/Library/Application Support/AmbientContext is refused.

Python 3 standard library only.
"""
import argparse
import base64
import copy
import datetime
import hmac
import json
import os
import re
import secrets
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROTOCOL = "0.2.0"
MCP_VERSION = "2026-07-28"
LEGACY_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]
EXTENSION = "io.github.ambientcontextprotocol/context"
CURRENT_URI = "ambient://current"
LOCATION_TEMPLATE = "ambient://location/{id}"
LOCATION_PREFIX = "ambient://location/"
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"
ID_FORM = re.compile(r"\A[A-Za-z0-9_-]{1,128}\Z")
BODY_LIMIT = 1 << 20
DEAD_PID = 99999999  # Above any process id macOS or Linux hands out.
REAL_FOLDER = os.path.join("~", "Library", "Application Support", "AmbientContext")

# Each fault: what it does, the requirement it breaks, the checks of
# check.py that report it, and how they report it.
FAULTS = {
    # The descriptor (section 8).
    "descriptor-missing-field": ("the descriptor has no 'started'", "PR-018", ["descriptor-fields"], "FAIL"),
    "descriptor-name": ("the descriptor file is not named <bundle-id>.<pid>.json", "PR-017", ["descriptor-name"], "FAIL"),
    "descriptor-mode": ("the descriptor file is mode 0644", "PR-019", ["descriptor-file-mode"], "FAIL"),
    "folder-mode": ("the descriptor folder is mode 0755", "PR-019", ["descriptor-folder-mode"], "FAIL"),
    "stale-pid": ("the descriptor names a process that is not running", "PR-020", ["descriptor-pid"], "FAIL"),
    "descriptor-protocol": ("the descriptor's protocol is 0.1", "PR-028", ["descriptor-protocol"], "FAIL"),
    "endpoint-localhost": ("the descriptor's endpoint names localhost, not 127.0.0.1", "PR-031", ["endpoint-address"], "FAIL"),
    # Refusals (section 7.4).
    "no-token-check": ("any request is served, with or without the token", "PR-032", ["token-missing", "token-wrong"], "FAIL"),
    "token-prefix": ("a token that begins with the right one is accepted", "PR-032", ["token-wrong"], "FAIL"),
    "allow-origin": ("a request with an Origin header is served", "PR-033", ["origin-refused", "origin-before-token", "origin-options"], "FAIL"),
    "origin-after-token": ("the token is judged before the Origin header", "PR-033", ["origin-before-token", "origin-options"], "FAIL"),
    "origin-body": ("the 403 for an Origin header carries a body", "PR-033", ["origin-refused"], "FAIL"),
    "preflight-answered": ("a cross-origin OPTIONS is answered 204", "PR-033", ["origin-options"], "FAIL"),
    "cors-header": ("every response carries Access-Control-Allow-Origin", "PR-063", ["cors-headers"], "FAIL"),
    "no-405": ("a GET with the token is answered 200", "PR-065", ["method-not-post"], "FAIL"),
    "no-413": ("an oversized request is answered 400", "PR-065", ["oversized-request"], "FAIL"),
    "header-mismatch-accepted": ("MCP headers that are missing or disagree with the body are accepted", "PR-065", ["header-mismatch"], "FAIL"),
    "bad-meta-accepted": ("a request lacking protocolVersion or clientCapabilities in _meta is served", "PR-064", ["meta-version-required", "meta-capabilities-required"], "FAIL"),
    "bad-json-accepted": ("a body that is not a JSON-RPC request is answered 200", "PR-026", ["malformed-body"], "FAIL"),
    "unknown-method-200": ("an unknown method is answered with HTTP 200", "PR-026", ["unknown-method"], "FAIL"),
    "any-version-accepted": ("an unknown MCP version is served", "PR-026", ["unsupported-version"], "FAIL"),
    # Declaring and listing (sections 7.2 and 7.3).
    "no-discover-version": ("server/discover does not name MCP 2026-07-28", "PR-026", ["discover"], "FAIL"),
    "no-extension": ("server/discover does not declare the extension", "PR-066", ["discover-extension"], "FAIL"),
    "extension-version": ("server/discover declares the extension with version 0.1", "PR-066", ["discover-extension"], "FAIL"),
    "missing-current-resource": ("resources/list does not list ambient://current", "PR-024", ["resources-list"], "FAIL"),
    "two-contents": ("reading ambient://current returns two contents entries", "PR-024", ["read-current"], "FAIL"),
    "wrong-mime": ("the contents entry is text/plain", "PR-024", ["read-current"], "FAIL"),
    # The answer (sections 4.1 and 5).
    "extra-field": ("the answer has a fourth field, 'app'", "PR-047", ["current-fields"], "FAIL"),
    "wrong-protocol": ("the answer's protocol is 0.1", "PR-066", ["current-protocol"], "FAIL"),
    "instance-mismatch": ("the answer's instance differs from the descriptor's", "PR-040", ["current-instance"], "FAIL"),
    "empty-children": ("an element sends an empty children list", "PR-048", ["element-fields"], "FAIL"),
    "missing-role": ("an element has no role", "PR-048", ["element-fields"], "FAIL"),
    "bad-id": ("an id contains a slash", "PR-059", ["id-form"], "FAIL"),
    "duplicate-id": ("two elements share an id", "PR-059", ["ids-unique"], "FAIL"),
    "root-not-application": ("the root is a Window", "PR-049", ["roles"], "FAIL"),
    "nested-application": ("an element below the root is an Application", "PR-049", ["roles"], "FAIL"),
    "unknown-role": ("an element has the role Button", "PR-049", ["roles"], "FAIL"),
    "state-false": ("an element sends focused: false", "PR-050", ["states-true-only"], "FAIL"),
    "focus-gap": ("an element is focused and its parent, below the root, is not", "PR-051", ["focus-path"], "FAIL"),
    "two-focused": ("two siblings are focused", "PR-051", ["focus-path"], "FAIL"),
    "two-hovered": ("two elements are hovered", "PR-053", ["hovered-single"], "FAIL"),
    "bad-content-block": ("a text content block has no text", "PR-005", ["content-blocks"], "FAIL"),
    # Locations (sections 4.2 and 6).
    "locate-bad-state": ("a location's state is 'hidden'", "PR-011", ["locate-issued"], "FAIL"),
    "locate-no-rects": ("a visible location has no rectangles", "PR-011", ["locate-issued"], "FAIL"),
    "locate-unknown-answered": ("an id never issued gets a location", "PR-060", ["locate-never-issued"], "FAIL"),
    # Older clients (sections 7.1 and 7.6).
    "legacy-extension-misplaced": ("the initialize result declares the extension under capabilities.extensions", "PR-066", ["legacy-extension"], "FAIL"),
    "legacy-read-refused": ("an older client's resources/read is refused", "PR-025", ["legacy-read"], "FAIL"),
    # Things a provider should do, and a slow answer: warned about, not failed.
    "no-ping": ("ping is not answered", "PR-026", ["ping"], "WARN"),
    "no-legacy": ("the initialize handshake is not answered", "PR-026", ["legacy-initialize"], "WARN"),
    "slow": ("the answer to current takes 1.2 seconds", "PR-004", ["current-time"], "WARN"),
}

# The tree served. Every optional field and every block type appears once.
TREE = {
    "id": "app", "role": "Application", "title": "Fake Notes",
    "children": [
        {"id": "w-1", "role": "Window", "title": "Launch plan", "focused": True, "children": [
            {"id": "doc-1", "role": "Document", "subrole": "note", "title": "Launch plan", "focused": True,
             "url": "file:///Users/ada/notes/launch-plan.md",
             "content": [{"type": "resource_link", "uri": "file:///Users/ada/notes/launch-plan.md", "name": "launch-plan.md"}],
             "attributes": {"words": 412},
             "children": [
                 {"id": "h-1", "role": "Heading", "title": "Launch plan"},
                 {"id": "p-1", "role": "Text", "focused": True,
                  "content": [{"type": "text", "text": "The private paragraph the cursor is in."}],
                  "children": [
                      {"id": "sel-1", "role": "Text", "selected": True,
                       "content": [{"type": "text", "text": "private paragraph"}],
                       "attributes": {"lines": {"start": 3, "end": 3}}},
                  ]},
                 {"id": "link-1", "role": "Link", "title": "Budget", "url": "https://example.com/budget", "hovered": True,
                  "attributes": {"related": [{"relation": "mentions", "id": "task-2"}]}},
                 {"id": "img-1", "role": "Image", "title": "Chart",
                  "content": [{"type": "image", "data": "iVBORw0KGgo=", "mimeType": "image/png"}]},
             ]},
            {"id": "list-1", "role": "List", "subrole": "thread", "title": "Comments", "children": [
                {"id": "c-1", "role": "Row", "subrole": "comment", "title": "Comment by Ada",
                 "attributes": {"author": "Ada"},
                 "content": [{"type": "text", "text": "A secret comment."}]},
            ]},
        ]},
        {"id": "w-2", "role": "Window", "subrole": "pane", "title": "Tasks", "visible": False, "children": [
            {"id": "table-1", "role": "Table", "children": [
                {"id": "task-1", "role": "Row", "subrole": "task", "selected": True, "children": [
                    {"id": "cell-1", "role": "Cell", "title": "Write the announcement"},
                ]},
                {"id": "task-2", "role": "Row", "subrole": "task", "title": "Book the room"},
            ]},
            {"id": "group-1", "role": "Group", "children": [
                {"id": "page-1", "role": "Page", "title": "Page 1"},
            ]},
        ]},
    ],
}

# Where things are. An id in the tree and not here cannot be placed.
LOCATIONS = {
    "sel-1": {"state": "visible", "rects": [{"x": 425, "y": 233, "w": 480, "h": 20}, {"x": 425, "y": 253, "w": 120, "h": 20}],
              "window": 4711, "avoid": {"x": 400, "y": 80, "w": 520, "h": 900}, "edge": "right"},
    "p-1": {"state": "visible", "rects": [{"x": 425, "y": 213, "w": 480.5, "h": 60}], "window": 4711},
    "doc-1": {"state": "visible", "rects": [{"x": 400, "y": 80, "w": 520, "h": 900}], "window": 4711},
    "task-1": {"state": "offscreen"},
    "gone-1": {"state": "gone"},  # Issued earlier in this run and since deleted.
}


def find(element, identifier):
    if element.get("id") == identifier:
        return element
    for child in element.get("children", []):
        found = find(child, identifier)
        if found:
            return found
    return None


def build_tree(faults, tree=None):
    """The tree to serve, with the faults that concern it applied."""
    root = copy.deepcopy(tree if tree is not None else TREE)
    if tree is not None:
        return root
    if "empty-children" in faults:
        find(root, "h-1")["children"] = []
    if "missing-role" in faults:
        del find(root, "h-1")["role"]
    if "bad-id" in faults:
        find(root, "h-1")["id"] = "h/1"
    if "duplicate-id" in faults:
        find(root, "h-1")["id"] = "task-2"
    if "root-not-application" in faults:
        root["role"] = "Window"
    if "nested-application" in faults:
        find(root, "group-1")["role"] = "Application"
    if "unknown-role" in faults:
        find(root, "h-1")["role"] = "Button"
    if "state-false" in faults:
        find(root, "w-2")["focused"] = False
    if "focus-gap" in faults:
        del find(root, "doc-1")["focused"]
    if "two-focused" in faults:
        find(root, "list-1")["focused"] = True
    if "two-hovered" in faults:
        find(root, "img-1")["hovered"] = True
    if "bad-content-block" in faults:
        find(root, "c-1")["content"] = [{"type": "text"}]
    return root


def compact(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


class Answer:
    def __init__(self, status, body=b"", headers=None):
        self.status, self.body, self.headers = status, body, dict(headers or {})


def success(identifier, legacy, result):
    full = dict(result) if legacy else dict(result, resultType="complete")
    return Answer(200, compact({"jsonrpc": "2.0", "id": identifier, "result": full}).encode("utf-8"))


def failure(status, identifier, code, message):
    body = {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": message}}
    return Answer(status, compact(body).encode("utf-8"))


def decoded_header(value):
    """MCP carries a header value that is not plain ASCII as =?base64?...?=."""
    if value.startswith("=?base64?") and value.endswith("?=") and len(value) >= 11:
        try:
            return base64.b64decode(value[9:-2], validate=True).decode("utf-8")
        except ValueError:
            return value
    return value


class FakeProvider:
    """The provider: a listener, a descriptor and the answers."""

    def __init__(self, directory, faults=(), delay=0.0, locate=True, redirect=False, keep_descriptor=False,
                 path="/mcp", port=0, tree=None, app_id="org.example.fake-notes"):
        unknown = sorted(set(faults) - set(FAULTS))
        if unknown:
            raise ValueError("unknown fault: " + ", ".join(unknown))
        if not path.startswith("/") or "?" in path or "#" in path:
            raise ValueError("the path must begin with / and carry no query or fragment")
        real = os.path.realpath(os.path.expanduser(REAL_FOLDER))
        target = os.path.realpath(os.path.expanduser(directory))
        if target == real or target.startswith(real + os.sep):
            raise ValueError("the fake provider does not write to the real descriptor folder")
        self.directory = target
        self.faults = frozenset(faults)
        self.delay = max(delay, 1.2) if "slow" in self.faults else delay
        self.locate = locate
        self.redirect = redirect
        self.keep_descriptor = keep_descriptor
        self.path = path
        self.port = port
        self.app = {"id": app_id, "name": "Fake Notes", "version": "0.2.0"}
        self.token = secrets.token_urlsafe(32)
        self.instance = secrets.token_hex(8)
        self.root = build_tree(self.faults, tree)
        self.descriptor_path = None
        self.endpoint = None
        self._server = None
        self._thread = None

    # -- lifecycle

    def start(self):
        """Opens the listener, then writes the descriptor. Returns its path."""
        provider = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "FakeProvider"
            sys_version = ""

            def log_message(self, *arguments):
                pass  # Neither the token nor anything from an answer is logged.

            def serve(self):
                answer = provider.respond(self.command, self.path, self.headers, self.rfile)
                if "cors-header" in provider.faults:
                    answer.headers["Access-Control-Allow-Origin"] = "*"
                self.send_response(answer.status)
                if answer.body:
                    answer.headers.setdefault("Content-Type", "application/json")
                answer.headers["Content-Length"] = str(len(answer.body))
                answer.headers["Connection"] = "close"
                for name, value in answer.headers.items():
                    self.send_header(name, value)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(answer.body)
                self.close_connection = True

            do_GET = do_POST = do_PUT = do_DELETE = do_OPTIONS = do_HEAD = do_PATCH = serve

        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        host = "localhost" if "endpoint-localhost" in self.faults else "127.0.0.1"
        self.endpoint = "http://%s:%d%s" % (host, self.port, self.path)
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self._thread.start()
        self._write_descriptor()
        return self.descriptor_path

    def _write_descriptor(self):
        if not os.path.isdir(self.directory):
            os.makedirs(self.directory, mode=0o700)
            os.chmod(self.directory, 0o700)
        if "folder-mode" in self.faults:
            os.chmod(self.directory, 0o755)
        pid = DEAD_PID if "stale-pid" in self.faults else os.getpid()
        descriptor = {
            "protocol": "0.1" if "descriptor-protocol" in self.faults else PROTOCOL,
            "app": self.app,
            "pid": pid,
            "instance": self.instance,
            "endpoint": self.endpoint,
            "token": self.token,
            "started": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if "descriptor-missing-field" in self.faults:
            del descriptor["started"]
        name = "%s.%d.json" % (self.app["id"], pid)
        if "descriptor-name" in self.faults:
            name = "provider.json"
        final = os.path.join(self.directory, name)
        # To a temporary name in the same folder, then renamed into place.
        temporary = os.path.join(self.directory, ".%s.%s.tmp" % (name, secrets.token_hex(4)))
        handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(handle, "w") as stream:
            json.dump(descriptor, stream, indent=2)
            stream.write("\n")
        os.chmod(temporary, 0o644 if "descriptor-mode" in self.faults else 0o600)
        os.replace(temporary, final)
        self.descriptor_path = final

    def stop(self):
        """Removes the descriptor and closes the listener."""
        if self.descriptor_path and not self.keep_descriptor:
            try:
                os.remove(self.descriptor_path)
            except FileNotFoundError:
                pass
        self.descriptor_path = None
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    # -- one request in, one response out

    def respond(self, http_method, path, headers, body_stream):
        faults = self.faults
        has_origin = headers.get("Origin") is not None
        authorization = headers.get("Authorization")
        expected = "Bearer " + self.token
        if "no-token-check" in faults:
            authorized = True
        elif authorization is None:
            authorized = False
        elif "token-prefix" in faults:
            authorized = authorization.startswith(expected)
        else:
            authorized = hmac.compare_digest(authorization.encode("utf-8"), expected.encode("utf-8"))

        # Origin first, so that a web page learns nothing else.
        if "origin-after-token" in faults and not authorized:
            return Answer(401, headers={"WWW-Authenticate": "Bearer"})
        if has_origin and "allow-origin" not in faults:
            if "preflight-answered" in faults and http_method == "OPTIONS":
                return Answer(204)
            if "origin-body" in faults:
                return Answer(403, b'{"error":"origin not allowed"}')
            return Answer(403)
        if not authorized:
            return Answer(401, headers={"WWW-Authenticate": "Bearer"})

        moved = self.path.rstrip("/") + "/moved"
        if self.redirect and path == self.path:
            return Answer(307, headers={"Location": moved})
        if path != (moved if self.redirect else self.path):
            return Answer(404)
        if http_method != "POST":
            if "no-405" in faults and http_method == "GET":
                return Answer(200, b"{}")
            return Answer(405, headers={"Allow": "POST"})

        try:
            length = int(headers.get("Content-Length") or "0")
        except ValueError:
            return Answer(400)
        if length < 0:
            return Answer(400)
        if length > BODY_LIMIT:
            return Answer(400 if "no-413" in faults else 413)
        body = body_stream.read(length) if length else b""

        try:
            message = json.loads(body.decode("utf-8"))
        except ValueError:
            message = None
        if not isinstance(message, dict):
            if "bad-json-accepted" in faults:
                return success(None, False, {})
            return failure(400, None, -32700, "Parse error")
        identifier = message.get("id")
        if isinstance(identifier, bool) or not isinstance(identifier, (str, int, float)):
            identifier = None
        method = message.get("method")
        if message.get("jsonrpc") != "2.0" or not isinstance(method, str):
            if "bad-json-accepted" in faults:
                return success(identifier, False, {})
            return failure(400, identifier, -32600, "Invalid request")
        if identifier is None:
            return Answer(202)  # A notification asks for nothing.

        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
        header = headers.get("MCP-Protocol-Version")
        declared = meta.get(META_VERSION) if isinstance(meta.get(META_VERSION), str) else None
        # An older client names its revision in the header alone, or not at all.
        legacy = method == "initialize" or (declared is None and (header is None or header in LEGACY_VERSIONS))
        if not legacy:
            refusal = self.validate(headers, method, params, meta, identifier)
            if refusal:
                return refusal
        return self.dispatch(method, params, identifier, legacy)

    def validate(self, headers, method, params, meta, identifier):
        """The checks MCP 2026-07-28 puts on every request."""
        faults = self.faults
        lenient_meta = "bad-meta-accepted" in faults
        lenient_headers = "header-mismatch-accepted" in faults
        declared = meta.get(META_VERSION)
        if not isinstance(declared, str):
            if not lenient_meta:
                return failure(400, identifier, -32602, "Missing %s in _meta" % META_VERSION)
            declared = MCP_VERSION
        header = headers.get("MCP-Protocol-Version")
        if not lenient_headers:
            if header is None:
                return failure(400, identifier, -32020, "Header mismatch: MCP-Protocol-Version header is missing")
            if header != declared:
                return failure(400, identifier, -32020, "Header mismatch: MCP-Protocol-Version disagrees with the body")
        if declared != MCP_VERSION and "any-version-accepted" not in faults:
            return failure(400, identifier, -32022, "Unsupported protocol version")
        if not isinstance(meta.get(META_CAPABILITIES), dict) and not lenient_meta:
            return failure(400, identifier, -32602, "Missing %s in _meta" % META_CAPABILITIES)
        if lenient_headers:
            return None
        named = headers.get("Mcp-Method")
        if named is None:
            return failure(400, identifier, -32020, "Header mismatch: Mcp-Method header is missing")
        if named != method:
            return failure(400, identifier, -32020, "Header mismatch: Mcp-Method disagrees with the body")
        uri = params.get("uri")
        if method == "resources/read" and isinstance(uri, str):
            name = headers.get("Mcp-Name")
            if name is None:
                return failure(400, identifier, -32020, "Header mismatch: Mcp-Name header is missing")
            if decoded_header(name) != uri:
                return failure(400, identifier, -32020, "Header mismatch: Mcp-Name disagrees with the body")
        return None

    def dispatch(self, method, params, identifier, legacy):
        faults = self.faults
        version = "0.1" if "extension-version" in faults and method == "server/discover" else PROTOCOL
        extension = {EXTENSION: {"version": version}}
        server_info = {"name": self.app["name"], "version": self.app["version"]}

        if method == "initialize" and "no-legacy" not in faults:
            asked = params.get("protocolVersion")
            holder = "extensions" if "legacy-extension-misplaced" in faults else "experimental"
            return success(identifier, True, {
                "protocolVersion": asked if asked in LEGACY_VERSIONS else LEGACY_VERSIONS[0],
                "capabilities": {"resources": {}, holder: extension},
                "serverInfo": server_info,
            })
        if method == "ping" and "no-ping" not in faults:
            return success(identifier, legacy, {})
        if method == "server/discover" and not legacy:
            versions = LEGACY_VERSIONS if "no-discover-version" in faults else [MCP_VERSION] + LEGACY_VERSIONS
            capabilities = {"resources": {}}
            if "no-extension" not in faults:
                capabilities["extensions"] = extension
            return success(identifier, False, {
                "supportedVersions": versions, "capabilities": capabilities,
                "_meta": {META_SERVER_INFO: server_info},
            })
        if method == "resources/list":
            resources = [] if "missing-current-resource" in faults else [{
                "uri": CURRENT_URI, "name": "current", "title": "Current context",
                "description": "What the user has open and selected in this app, right now.",
                "mimeType": "application/json",
            }]
            return success(identifier, legacy, {"resources": resources})
        if method == "resources/templates/list":
            templates = [{
                "uriTemplate": LOCATION_TEMPLATE, "name": "location", "title": "Location of an element",
                "description": "Where an element from the current context is on screen.",
                "mimeType": "application/json",
            }] if self.locate else []
            return success(identifier, legacy, {"resourceTemplates": templates})
        if method == "resources/read":
            uri = params.get("uri")
            if not isinstance(uri, str):
                return failure(200, identifier, -32602, "Missing uri")
            text = None if (legacy and "legacy-read-refused" in faults) else self.read(uri)
            if text is None:
                # Earlier revisions used their own code for this.
                return failure(200, identifier, -32002 if legacy else -32602, "Resource not found")
            current = uri == CURRENT_URI and not legacy
            entry = {"uri": uri, "mimeType": "text/plain" if current and "wrong-mime" in faults else "application/json", "text": text}
            contents = [entry, entry] if current and "two-contents" in faults else [entry]
            return success(identifier, legacy, {"contents": contents})
        if "unknown-method-200" in faults and not legacy:
            return failure(200, identifier, -32601, "Method not found")
        return failure(200 if legacy else 404, identifier, -32601, "Method not found")

    def read(self, uri):
        """The JSON document a resource holds, or None when there is none."""
        faults = self.faults
        if uri == CURRENT_URI:
            if self.delay:
                time.sleep(self.delay)
            answer = {
                "protocol": "0.1" if "wrong-protocol" in faults else PROTOCOL,
                "instance": self.instance + "-other" if "instance-mismatch" in faults else self.instance,
                "root": self.root,
            }
            if "extra-field" in faults:
                answer["app"] = {"id": self.app["id"], "name": self.app["name"]}
            return compact(answer)
        if not self.locate or not uri.startswith(LOCATION_PREFIX):
            return None
        identifier = uri[len(LOCATION_PREFIX):]
        if not ID_FORM.match(identifier):
            return None
        location = LOCATIONS.get(identifier)
        if location is None:
            if "locate-unknown-answered" in faults and find(self.root, identifier) is None:
                return compact({"id": identifier, "state": "gone"})
            return None
        location = dict(location, id=identifier)
        if "locate-bad-state" in faults and location["state"] == "offscreen":
            location["state"] = "hidden"
        if "locate-no-rects" in faults:
            location.pop("rects", None)
        return compact(location)


def main(argv=None):
    parser = argparse.ArgumentParser(description="A fake Ambient Context Protocol %s provider." % PROTOCOL)
    parser.add_argument("--directory", help="the folder the descriptor is written into (required; never the real one)")
    parser.add_argument("--fault", action="append", default=[], metavar="NAME", help="break one requirement; may be repeated")
    parser.add_argument("--list-faults", action="store_true", help="list the faults and exit")
    parser.add_argument("--delay", type=float, default=0.0, metavar="SECONDS", help="wait this long before answering current")
    parser.add_argument("--no-locate", action="store_true", help="offer no location template, as a provider that cannot report positions")
    parser.add_argument("--redirect", action="store_true", help="answer the endpoint with a 307 to another path, which a host must not follow")
    parser.add_argument("--keep-descriptor", action="store_true", help="leave the descriptor behind on exit, as a provider that crashed")
    parser.add_argument("--path", default="/mcp", help="the endpoint's path (default /mcp)")
    parser.add_argument("--port", type=int, default=0, help="the port to listen on (default: one the system assigns)")
    parser.add_argument("--tree", metavar="FILE", help="serve the root element in this JSON file instead of the built-in tree")
    arguments = parser.parse_args(argv)

    if arguments.list_faults:
        width = max(len(name) for name in FAULTS)
        for name, (what, requirement, checks, outcome) in FAULTS.items():
            print("%-*s  %s  %s  %s  (%s)" % (width, name, requirement, outcome, what, ", ".join(checks)))
        return 0
    if not arguments.directory:
        parser.error("--directory is required")

    tree = None
    if arguments.tree:
        with open(arguments.tree, encoding="utf-8") as handle:
            tree = json.load(handle)
    try:
        provider = FakeProvider(
            arguments.directory, faults=arguments.fault, delay=arguments.delay, locate=not arguments.no_locate,
            redirect=arguments.redirect, keep_descriptor=arguments.keep_descriptor, path=arguments.path,
            port=arguments.port, tree=tree,
        )
    except ValueError as error:
        parser.error(str(error))

    stopping = threading.Event()
    for name in ("SIGINT", "SIGTERM"):
        signal.signal(getattr(signal, name), lambda *_: stopping.set())
    descriptor = provider.start()
    try:
        print("descriptor: %s" % descriptor, flush=True)
        print("answering on %s; Ctrl-C to stop" % provider.endpoint, flush=True)
        stopping.wait()
    finally:
        provider.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
