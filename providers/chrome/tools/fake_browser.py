#!/usr/bin/env python3
"""Stands in for the browser and its extension, to test the helper alone.

Starts the helper as a browser would, with pipes on its standard input
and output, and answers each question it asks with one fixed page. The
descriptor goes in a temporary folder, never the real one. Prints the
descriptor's path, then runs until interrupted or, with --check, runs the
outside check against the helper and exits with its status.

    python3 providers/chrome/tools/fake_browser.py <path to helper> [--check] [--silent]

--silent answers nothing, to see what the helper says when the extension
does not answer in time.
"""

import json
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time

STATE = {
    "window": {"id": 8, "focused": True},
    "tab": {"id": 44, "title": "Uniform Resource Identifier (URI): Generic Syntax", "url": "https://www.rfc-editor.org/rfc/rfc3986"},
    "selection": "A URI is a sequence of characters.",
    "readable": True,
}


def serve(helper, silent):
    while True:
        head = helper.stdout.read(4)
        if len(head) < 4:
            return
        (length,) = struct.unpack("=I", head)
        message = json.loads(helper.stdout.read(length))
        if silent or message.get("type") != "current":
            continue
        body = json.dumps({"type": "state", "id": message["id"], "state": STATE}).encode()
        helper.stdin.write(struct.pack("=I", len(body)) + body)
        helper.stdin.flush()


def main():
    arguments = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(arguments) != 1:
        sys.exit(__doc__)
    folder = os.path.join(tempfile.mkdtemp(prefix="acp-chrome-"), "providers")
    environment = dict(os.environ, AMBIENT_CONTEXT_TEST_APP="org.example.browser", AMBIENT_CONTEXT_TEST_DIRECTORY=folder)
    helper = subprocess.Popen(
        [arguments[0], "chrome-extension://test/"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=environment
    )
    threading.Thread(target=serve, args=(helper, "--silent" in sys.argv), daemon=True).start()

    name = "org.example.browser.%d.for.%d.json" % (os.getpid(), helper.pid)
    path = os.path.join(folder, name)
    for _ in range(50):
        if os.path.exists(path):
            break
        time.sleep(0.1)
    else:
        helper.kill()
        sys.exit("the helper wrote no descriptor at %s" % path)
    print(path, flush=True)

    status = 0
    try:
        if "--check" in sys.argv:
            check = os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools", "conformance", "check.py")
            status = subprocess.call([sys.executable, check, path])
        else:
            helper.wait()
    except KeyboardInterrupt:
        pass
    # Closing the stream is how a browser tells its helper to stop.
    helper.stdin.close()
    helper.wait(timeout=5)
    if os.path.exists(path):
        print("FAIL  the helper left its descriptor behind", flush=True)
        status = 1
    else:
        print("the helper removed its descriptor on exit", flush=True)
    sys.exit(status)


if __name__ == "__main__":
    main()
