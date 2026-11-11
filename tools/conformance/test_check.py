"""Tests for the conformance check, run against the fake provider.

    python3 -m unittest tools/conformance/test_check.py

The fake provider writes its descriptor into a temporary folder; the real
descriptor folder is never touched.
"""
import copy
import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check  # noqa: E402
import fake_provider  # noqa: E402
from fake_provider import FAULTS, FakeProvider  # noqa: E402

CHECK = os.path.join(HERE, "check.py")
FAKE = os.path.join(HERE, "fake_provider.py")

# Text that must never reach the check's output: the fake tree's titles,
# content, addresses and attribute values.
PRIVATE = [
    "Fake Notes", "Launch plan", "private paragraph", "launch-plan.md", "example.com/budget",
    "Comment by Ada", "A secret comment", "iVBORw0KGgo", "Write the announcement", "Book the room",
    "mentions", "Ada",
]


class Running:
    """A fake provider for the length of a `with` block."""

    def __init__(self, **options):
        self.options = options

    def __enter__(self):
        self.folder = tempfile.TemporaryDirectory()
        self.provider = FakeProvider(os.path.join(self.folder.name, "providers"), **self.options)
        self.provider.descriptor = self.provider.start()
        return self.provider

    def __exit__(self, *_):
        self.provider.stop()
        self.folder.cleanup()


def by_name(results):
    return {item["name"]: item for item in results.items}


def not_passing(results):
    return {item["name"]: item["status"] for item in results.items if item["status"] != check.PASS}


class CleanProvider(unittest.TestCase):
    def test_every_check_passes(self):
        with Running() as provider:
            results = check.run(descriptor_path=provider.descriptor)
        self.assertEqual(not_passing(results), {})
        self.assertGreaterEqual(len(results.items), 40)
        for item in results.items:
            self.assertRegex(item["requirement"], r"\APR-\d{3}\Z")

    def test_every_requirement_named_holds_in_this_version(self):
        listing = subprocess.run(
            [sys.executable, os.path.join(HERE, "..", "requirements.py"), check.PROTOCOL],
            capture_output=True, text=True, cwd=os.path.join(HERE, "..", ".."), check=True,
        ).stdout
        holding = {line.split()[0] for line in listing.splitlines() if line.startswith("PR-")}
        with Running() as provider:
            results = check.run(descriptor_path=provider.descriptor)
        named = {item["requirement"] for item in results.items}
        self.assertEqual(named - holding, set())
        self.assertEqual({requirement for _what, requirement, _checks, _outcome in FAULTS.values()} - named, set())

    def test_by_endpoint_and_token(self):
        with Running() as provider:
            results = check.run(endpoint=provider.endpoint, token=provider.token,
                                instance=provider.instance, pid=os.getpid())
            self.assertEqual(not_passing(results), {})
            self.assertNotIn("descriptor-fields", by_name(results))
            without = check.run(endpoint=provider.endpoint, token=provider.token)
        self.assertEqual(not_passing(without), {"current-instance": check.SKIP})

    def test_a_path_of_the_providers_choice(self):
        with Running(path="/ambient") as provider:
            self.assertTrue(provider.endpoint.endswith("/ambient"))
            results = check.run(descriptor_path=provider.descriptor)
        self.assertEqual(not_passing(results), {})

    def test_without_locate_the_locate_checks_are_skipped(self):
        with Running(locate=False) as provider:
            results = check.run(descriptor_path=provider.descriptor)
        self.assertEqual(not_passing(results), {"locate-issued": check.SKIP, "locate-never-issued": check.SKIP})
        self.assertFalse(results.failed)

    def test_a_redirect_is_not_followed(self):
        with Running(redirect=True) as provider:
            results = check.run(descriptor_path=provider.descriptor)
        self.assertTrue(results.failed)
        self.assertIn("HTTP 307", by_name(results)["discover"]["detail"])

    def test_a_provider_that_is_not_there(self):
        with Running() as provider:
            endpoint, token = provider.endpoint, provider.token
        results = check.run(endpoint=endpoint, token=token, timeout=1.0)
        self.assertEqual(by_name(results)["endpoint-answers"]["status"], check.FAIL)

    def test_the_token_is_not_sent_off_this_machine(self):
        results = check.run(endpoint="http://192.0.2.1:9/mcp", token="secret-token", timeout=0.5)
        names = by_name(results)
        self.assertEqual(names["endpoint-address"]["status"], check.FAIL)
        self.assertEqual(names["endpoint-answers"]["status"], check.SKIP)
        self.assertEqual(len(results.items), 3)


class Faults(unittest.TestCase):
    def test_each_fault_trips_its_own_checks_and_no_other(self):
        self.assertGreaterEqual(len(FAULTS), 15)
        for name, (_what, requirement, checks, outcome) in FAULTS.items():
            with self.subTest(fault=name):
                with Running(faults=[name]) as provider:
                    results = check.run(descriptor_path=provider.descriptor)
                found = by_name(results)
                for check_name in checks:
                    self.assertIn(check_name, found)
                    self.assertEqual(found[check_name]["status"], outcome, found[check_name]["detail"])
                    self.assertEqual(found[check_name]["requirement"], requirement)
                # Nothing else fails; a check that depends on a missing
                # part may be skipped.
                others = {key: status for key, status in not_passing(results).items() if key not in checks}
                self.assertEqual({key: status for key, status in others.items() if status != check.SKIP}, {})
                self.assertEqual(results.failed, outcome == check.FAIL)

    def test_an_unknown_fault_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                FakeProvider(folder, faults=["no-such-fault"])

    def test_a_slow_answer_is_warned_about_not_failed(self):
        with Running(delay=0.25) as provider:
            results = check.run(descriptor_path=provider.descriptor, slow=0.1)
        self.assertEqual(not_passing(results), {"current-time": check.WARN})
        self.assertFalse(results.failed)

    def test_an_answer_slower_than_the_time_limit_fails(self):
        with Running(delay=1.0) as provider:
            results = check.run(descriptor_path=provider.descriptor, timeout=0.3)
        self.assertEqual(by_name(results)["read-current"]["status"], check.FAIL)
        self.assertIn("timed out", by_name(results)["read-current"]["detail"])


class Privacy(unittest.TestCase):
    def assert_private(self, text, provider):
        self.assertNotIn(provider.token, text)
        for secret in PRIVATE:
            self.assertNotIn(secret, text)

    def test_nothing_private_is_printed(self):
        with Running() as provider:
            results = check.run(descriptor_path=provider.descriptor)
            self.assert_private(check.render(results) + json.dumps(results.items), provider)

    def test_nothing_private_is_printed_when_checks_fail(self):
        for name in FAULTS:
            if name == "slow":
                continue
            with self.subTest(fault=name):
                with Running(faults=[name]) as provider:
                    results = check.run(descriptor_path=provider.descriptor)
                    self.assert_private(check.render(results) + json.dumps(results.items), provider)

    def test_a_malformed_tree_is_described_by_position_only(self):
        root = {"id": "app", "role": "Application", "title": "Secret title", "children": [
            {"id": "my secret id", "role": "My Secret Role", "selected": "secret state",
             "content": [{"type": "secret type"}, "secret block"], "attributes": "secret attributes"},
            "secret element",
        ]}
        found, count = check.check_tree(root)
        self.assertEqual(count, 3)
        text = json.dumps(found)
        self.assertNotIn("ecret", text)
        self.assertIn("root/0", text)
        for name in ("element-fields", "id-form", "roles", "states-true-only", "content-blocks"):
            self.assertTrue(found[name], name)


class Tree(unittest.TestCase):
    """The rules of section 5, on trees built by hand."""

    def problems(self, edit):
        root = copy.deepcopy(fake_provider.TREE)
        edit(root)
        found, _count = check.check_tree(root)
        return {name for name, problems in found.items() if problems}

    def test_the_built_in_tree_is_valid(self):
        self.assertEqual(self.problems(lambda root: None), set())

    def test_the_specifications_example_is_valid(self):
        path = os.path.join(HERE, "..", "..", "docs", "spec", "elements.md")
        with open(path, encoding="utf-8") as handle:
            block = handle.read().split("```json\n", 1)[1].split("```", 1)[0]
        found, count = check.check_tree(json.loads(block)["root"])
        self.assertEqual(count, 7)
        self.assertEqual({name for name, problems in found.items() if problems}, set())

    def test_the_root_may_be_focused_or_not(self):
        self.assertEqual(self.problems(lambda root: root.update(focused=True)), set())

    def test_no_focus_at_all_is_valid(self):
        def clear(element):
            element.pop("focused", None)
            for child in element.get("children", []):
                clear(child)
        self.assertEqual(self.problems(clear), set())

    def test_two_focused_windows(self):
        self.assertEqual(self.problems(lambda root: root["children"][1].update(focused=True)), {"focus-path"})

    def test_focus_below_an_unfocused_window(self):
        def edit(root):
            root["children"][1]["children"][0]["focused"] = True
        self.assertEqual(self.problems(edit), {"focus-path"})

    def test_a_long_id(self):
        self.assertEqual(self.problems(lambda root: root["children"][0].update(id="a" * 128)), set())
        self.assertEqual(self.problems(lambda root: root["children"][0].update(id="a" * 129)), {"id-form"})
        self.assertEqual(self.problems(lambda root: root["children"][0].update(id="")), {"id-form"})
        self.assertEqual(self.problems(lambda root: root["children"][0].update(id="a\n")), {"id-form"})
        self.assertEqual(self.problems(lambda root: root["children"][0].update(id=7)), {"element-fields"})

    def test_states_sent_with_other_values(self):
        for state in ("selected", "focused", "hovered"):
            for value in (False, 1, "true", None):
                self.assertEqual(
                    self.problems(lambda root: root["children"][1].update({state: value})), {"states-true-only"})
        self.assertEqual(self.problems(lambda root: root["children"][0].update(visible=False)), set())
        self.assertEqual(self.problems(lambda root: root["children"][0].update(visible="no")), {"element-fields"})

    def test_fields_of_the_wrong_type(self):
        for field, value in (("subrole", ""), ("url", ""), ("title", 3), ("children", {}), ("attributes", []),
                             ("content", {}), ("attributes", {"author": 3}), ("attributes", {"related": [1]})):
            self.assertEqual(self.problems(lambda root: root["children"][0].update({field: value})),
                             {"element-fields"}, field)

    def test_fields_not_in_the_specification_are_ignored(self):
        self.assertEqual(self.problems(lambda root: root["children"][0].update(mood="calm")), set())

    def test_content_blocks(self):
        good = [
            {"type": "text", "text": ""}, {"type": "image", "data": "", "mimeType": "image/png"},
            {"type": "audio", "data": "", "mimeType": "audio/wav"}, {"type": "resource_link", "uri": "x:", "name": "x"},
            {"type": "resource", "resource": {"uri": "x:", "text": ""}},
        ]
        self.assertEqual(self.problems(lambda root: root.update(content=good)), set())
        for bad in ({"type": "video"}, {"text": "x"}, {"type": "image", "data": ""}, {"type": "resource_link", "uri": "x:"},
                    {"type": "resource"}, "text"):
            self.assertEqual(self.problems(lambda root: root.update(content=[bad])), {"content-blocks"})


class Pieces(unittest.TestCase):
    def test_the_endpoint(self):
        self.assertEqual(check.parse_endpoint("http://127.0.0.1:53124/mcp"), ("127.0.0.1", 53124, "/mcp", [], []))
        for endpoint in ("http://localhost:53124/mcp", "http://0.0.0.0:53124/mcp", "https://127.0.0.1:53124/mcp",
                         "http://127.0.0.1/mcp", "http://[::1]:53124/mcp", "http://user@127.0.0.1:53124/mcp", 7):
            self.assertTrue(check.parse_endpoint(endpoint)[3], endpoint)
        for endpoint in ("http://127.0.0.1:53124", "http://127.0.0.1:53124/mcp?x=1", "http://127.0.0.1:53124/mcp#x"):
            host, _port, _path, address, path = check.parse_endpoint(endpoint)
            self.assertEqual((host, address), ("127.0.0.1", []))
            self.assertTrue(path, endpoint)

    def test_locations(self):
        rect = {"x": 1, "y": 2.5, "w": 3, "h": 4}
        good = [
            {"id": "a", "state": "visible", "rects": [rect], "window": 7, "avoid": rect, "edge": "left"},
            {"id": "a", "state": "offscreen"}, {"id": "a", "state": "gone"}, {"id": "a", "state": "gone", "later": 1},
        ]
        for location in good:
            self.assertEqual(check.location_problems(location, "a"), [])
        bad = [
            {"id": "b", "state": "gone"}, {"id": "a"}, {"id": "a", "state": "hidden"}, {"id": "a", "state": "visible"},
            {"id": "a", "state": "visible", "rects": []}, {"id": "a", "state": "visible", "rects": [{"x": 1}]},
            {"id": "a", "state": "visible", "rects": [dict(rect, x=True)]},
            {"id": "a", "state": "gone", "window": "7"}, {"id": "a", "state": "gone", "edge": "middle"},
            {"id": "a", "state": "gone", "avoid": [1, 2, 3, 4]}, [],
        ]
        for location in bad:
            self.assertTrue(check.location_problems(location, "a"), location)

    def test_an_event_stream_answer_is_read(self):
        body = b'event: message\r\ndata: {"jsonrpc":"2.0","id":1,\r\ndata: "result":{}}\r\n\r\n'
        response = check.Response(200, [("Content-Type", "text/event-stream")], body)
        self.assertEqual(response.result(), {})

    def test_a_descriptor_that_is_not_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "x.json")
            with open(path, "w") as handle:
                handle.write("{half a file")
            results = check.run(descriptor_path=path)
        self.assertEqual([(item["name"], item["status"]) for item in results.items], [("descriptor-fields", check.FAIL)])


class CommandLine(unittest.TestCase):
    def start(self, folder, *arguments):
        process = subprocess.Popen(
            [sys.executable, FAKE, "--directory", os.path.join(folder, "providers"), *arguments],
            stdout=subprocess.PIPE, text=True,
        )
        self.addCleanup(process.stdout.close)
        self.addCleanup(process.wait)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        first = process.stdout.readline().strip()
        self.assertTrue(first.startswith("descriptor: "), first)
        return process, first[len("descriptor: "):]

    def run_check(self, *arguments):
        return subprocess.run([sys.executable, CHECK, *arguments], capture_output=True, text=True)

    def test_the_clean_provider_passes_and_the_descriptor_goes_at_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            process, descriptor = self.start(folder)
            with open(descriptor) as handle:
                token = json.load(handle)["token"]
            done = self.run_check(descriptor)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            lines = done.stdout.splitlines()
            self.assertIn("0 failed", lines[-1])
            for line in lines[:-1]:
                self.assertRegex(line, r"\A(PASS|FAIL|WARN|SKIP)  PR-\d{3}  [a-z0-9-]+ +\S")
            self.assertNotIn(token, done.stdout + done.stderr)
            for secret in PRIVATE:
                self.assertNotIn(secret, done.stdout)

            process.send_signal(signal.SIGTERM)
            self.assertEqual(process.wait(timeout=10), 0)
            self.assertFalse(os.path.exists(descriptor))
            self.assertEqual(os.listdir(os.path.dirname(descriptor)), [])

    def test_a_fault_exits_nonzero_and_json_names_the_requirement(self):
        with tempfile.TemporaryDirectory() as folder:
            process, descriptor = self.start(folder, "--fault", "two-hovered", "--fault", "duplicate-id")
            done = self.run_check(descriptor, "--json")
            process.send_signal(signal.SIGINT)
            process.wait(timeout=10)
        self.assertEqual(done.returncode, 1)
        report = json.loads(done.stdout)
        self.assertEqual(report["protocol"], "0.2.0")
        self.assertEqual(report["summary"]["fail"], 2)
        failed = {(item["requirement"], item["name"]) for item in report["results"] if item["status"] == "FAIL"}
        self.assertEqual(failed, {("PR-053", "hovered-single"), ("PR-059", "ids-unique")})

    def test_the_faults_are_listed(self):
        done = subprocess.run([sys.executable, FAKE, "--list-faults"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0)
        self.assertEqual([line.split()[0] for line in done.stdout.splitlines()], list(FAULTS))

    def test_the_directory_is_required_and_never_the_real_one(self):
        done = subprocess.run([sys.executable, FAKE], capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)
        self.assertIn("--directory is required", done.stderr)
        real = os.path.expanduser("~/Library/Application Support/AmbientContext/providers")
        existed = os.path.exists(real)
        done = subprocess.run([sys.executable, FAKE, "--directory", real], capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)
        self.assertIn("real descriptor folder", done.stderr)
        self.assertEqual(os.path.exists(real), existed)

    def test_the_check_needs_a_descriptor_or_an_endpoint(self):
        self.assertEqual(self.run_check().returncode, 2)
        self.assertEqual(self.run_check("--endpoint", "http://127.0.0.1:1/mcp").returncode, 2)


if __name__ == "__main__":
    unittest.main()
