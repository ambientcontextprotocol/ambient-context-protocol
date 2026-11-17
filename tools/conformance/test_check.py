"""Tests for the conformance check, run against the fake provider.

    python3 -m unittest tools/conformance/test_check.py

The fake provider writes its descriptor into a temporary folder; the real
descriptor folder is never touched.
"""
import concurrent.futures
import copy
import functools
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
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
    "mentions", "Ada", "paragraph 2", "comment 1",
]

# A run that does not hold the watch open cannot judge the keep-alive.
UNHELD = {"watch-keepalive": check.SKIP}
# For a run that does: the fake provider's comment lines come this often,
# the check asks for one this often and holds the watch this long.
BRISK = {"keepalive": 0.1}
HELD = {"watch_hold": 0.8, "watch_keepalive": 0.4}
# The faults the check sees only if the tree changes while it watches.
NEED_A_CHANGE = ("watch-notice-content", "watch-wrong-uri", "watch-flood")
NOT_OFFERED = "the provider does not offer watch"


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


def quick(**arguments):
    """The check with the watch not held open, which is what most tests need."""
    return check.run(watch_hold=0, **arguments)


def driven(provider, wait=0.6):
    """The checks that need the app driven, with the fake provider as the app."""
    results = check.Results()
    with check.Watch.from_descriptor(provider.descriptor, timeout=2.0) as watch:
        watch.first_message()
        check.drive_changes(watch, provider.change, results, burst=lambda: provider.burst(10), wait=wait)
        check.drive_hover(watch, provider.hover, results, quiet=0.35)
        check.drive_stop(watch, provider.stop, results, wait=0.5)
    return results


@functools.lru_cache(maxsize=None)
def with_fault(name):
    """What the check, and for a DRIVE fault the driven checks, make of one fault.

    Returns (results, driven results or None, everything printable, the token).
    """
    options, arguments = {"faults": (name,)}, {"watch_hold": 0}
    if name in NEED_A_CHANGE:
        options.update(BRISK, change_every=0.15)
        arguments["watch_hold"] = 0.5
    elif name == "watch-no-keepalive":
        options.update(BRISK)
        arguments = HELD
    with Running(**options) as provider:
        results = check.run(descriptor_path=provider.descriptor, **arguments)
        text = check.render(results) + json.dumps(results.items)
        moved = None
        if FAULTS[name][3] == "DRIVE":
            moved = driven(provider)
            text += check.render(moved) + json.dumps(moved.items)
        return results, moved, text, provider.token


def every_fault():
    """Each fault's outcome. Worked out side by side, since most of the time is spent waiting."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        return list(zip(FAULTS, pool.map(with_fault, FAULTS)))


class CleanProvider(unittest.TestCase):
    def test_every_check_passes(self):
        with Running(**BRISK) as provider:
            results = check.run(descriptor_path=provider.descriptor, **HELD)
        self.assertEqual(not_passing(results), {})
        self.assertGreaterEqual(len(results.items), 50)
        for item in results.items:
            self.assertRegex(item["requirement"], r"\APR-\d{3}\Z")

    def test_every_requirement_named_holds_in_this_version(self):
        listing = subprocess.run(
            [sys.executable, os.path.join(HERE, "..", "requirements.py"), check.PROTOCOL],
            capture_output=True, text=True, cwd=os.path.join(HERE, "..", ".."), check=True,
        ).stdout
        holding = {line.split()[0] for line in listing.splitlines() if line.startswith("PR-")}
        with Running() as provider:
            results = quick(descriptor_path=provider.descriptor)
            moved = driven(provider)
        with Running(watch=False) as provider:
            without = quick(descriptor_path=provider.descriptor)
        named = {item["requirement"] for item in results.items + moved.items + without.items}
        self.assertEqual(named - holding, set())
        self.assertLessEqual({"PR-08%d" % number for number in range(8)}, named)
        self.assertEqual({requirement for _what, requirement, _checks, _outcome in FAULTS.values()} - named, set())

    def test_by_endpoint_and_token(self):
        with Running() as provider:
            results = quick(endpoint=provider.endpoint, token=provider.token,
                            instance=provider.instance, pid=os.getpid())
            self.assertEqual(not_passing(results), UNHELD)
            self.assertNotIn("descriptor-fields", by_name(results))
            without = quick(endpoint=provider.endpoint, token=provider.token)
        self.assertEqual(not_passing(without), dict(UNHELD, **{"current-instance": check.SKIP}))

    def test_a_path_of_the_providers_choice(self):
        with Running(path="/ambient") as provider:
            self.assertTrue(provider.endpoint.endswith("/ambient"))
            results = quick(descriptor_path=provider.descriptor)
        self.assertEqual(not_passing(results), UNHELD)

    def test_without_locate_the_locate_checks_are_skipped(self):
        with Running(locate=False) as provider:
            results = quick(descriptor_path=provider.descriptor)
        self.assertEqual(not_passing(results),
                         dict(UNHELD, **{"locate-issued": check.SKIP, "locate-never-issued": check.SKIP}))
        self.assertFalse(results.failed)

    def test_without_display_every_check_still_passes(self):
        with Running(display=False) as provider:
            results = quick(descriptor_path=provider.descriptor)
        self.assertEqual(not_passing(results), UNHELD)
        self.assertIn("no display", by_name(results)["current-display"]["detail"])

    def test_a_display_problem_names_the_field_and_never_quotes_it(self):
        with Running(faults=["display-two-lines"]) as provider:
            results = quick(descriptor_path=provider.descriptor)
        detail = by_name(results)["current-display"]["detail"]
        self.assertIn("display.detail", detail)
        self.assertNotIn("paragraph", detail)

    def test_a_redirect_is_not_followed(self):
        with Running(redirect=True) as provider:
            results = quick(descriptor_path=provider.descriptor)
        self.assertTrue(results.failed)
        self.assertIn("HTTP 307", by_name(results)["discover"]["detail"])
        self.assertEqual(by_name(results)["watch-served"]["status"], check.SKIP)

    def test_a_provider_that_is_not_there(self):
        with Running() as provider:
            endpoint, token = provider.endpoint, provider.token
        results = check.run(endpoint=endpoint, token=token, timeout=1.0)
        self.assertEqual(by_name(results)["endpoint-answers"]["status"], check.FAIL)

    def test_the_token_is_not_sent_off_this_machine(self):
        results = check.run(endpoint="http://192.0.2.2:9/mcp", token="secret-token", timeout=0.5)
        names = by_name(results)
        self.assertEqual(names["endpoint-address"]["status"], check.FAIL)
        self.assertEqual(names["endpoint-answers"]["status"], check.SKIP)
        self.assertEqual(len(results.items), 3)


class Faults(unittest.TestCase):
    def test_each_fault_trips_its_own_checks_and_no_other(self):
        self.assertGreaterEqual(len(FAULTS), 15)
        for name, (results, moved, _text, _token) in every_fault():
            _what, requirement, checks, outcome = FAULTS[name]
            with self.subTest(fault=name):
                if outcome == "DRIVE":
                    # The check sees nothing wrong. The driven checks do.
                    self.assertEqual({key: status for key, status in not_passing(results).items() if status != check.SKIP}, {})
                    results, outcome = moved, check.FAIL
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
            results = quick(descriptor_path=provider.descriptor, slow=0.1)
        self.assertEqual(not_passing(results), dict(UNHELD, **{"current-time": check.WARN}))
        self.assertFalse(results.failed)

    def test_an_answer_slower_than_the_time_limit_fails(self):
        with Running(delay=1.0) as provider:
            results = quick(descriptor_path=provider.descriptor, timeout=0.3)
        self.assertEqual(by_name(results)["read-current"]["status"], check.FAIL)
        self.assertIn("timed out", by_name(results)["read-current"]["detail"])


class Privacy(unittest.TestCase):
    def assert_private(self, text, token, instance=None):
        self.assertNotIn(token, text)
        if instance:
            self.assertNotIn(instance, text)
        for secret in PRIVATE:
            self.assertNotIn(secret, text)

    def test_nothing_private_is_printed(self):
        with Running(change_every=0.1, **BRISK) as provider:
            results = check.run(descriptor_path=provider.descriptor, **HELD)
            moved = driven(provider)
            text = check.render(results) + json.dumps(results.items) + check.render(moved) + json.dumps(moved.items)
            self.assert_private(text, provider.token, provider.instance)

    def test_nothing_private_is_printed_when_checks_fail(self):
        for name, (_results, _moved, text, token) in every_fault():
            with self.subTest(fault=name):
                self.assert_private(text, token)

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


class Watching(unittest.TestCase):
    """RFC-0006: the watch on current, with the fake provider as the app."""

    def open(self, provider, **options):
        watch = check.Watch.from_descriptor(provider.descriptor, timeout=2.0, **options).open()
        self.addCleanup(watch.close)
        return watch

    def eventually(self, test, seconds=2.0):
        deadline = time.monotonic() + seconds
        while not test() and time.monotonic() < deadline:
            time.sleep(0.01)
        return test()

    def test_a_provider_that_does_not_offer_watch(self):
        with Running(watch=False) as provider:
            results = quick(descriptor_path=provider.descriptor)
            self.assertEqual(provider.watches_opened, 0)
        found = by_name(results)
        self.assertEqual((found["watch-not-offered"]["status"], found["watch-not-offered"]["requirement"]), (check.PASS, "PR-081"))
        self.assertIn("HTTP 404, error -32601", found["watch-not-offered"]["detail"])
        self.assertEqual(not_passing(results), {name: check.SKIP for _requirement, name in check.WATCH_CHECKS})
        for _requirement, name in check.WATCH_CHECKS:
            self.assertEqual(found[name]["detail"], NOT_OFFERED)
        self.assertFalse(results.failed)

    def test_a_provider_that_offers_watch_is_not_judged_as_one_that_does_not(self):
        with Running() as provider:
            results = quick(descriptor_path=provider.descriptor)
        self.assertNotIn("watch-not-offered", by_name(results))

    def test_no_change_while_watching_passes_and_says_so(self):
        with Running() as provider:
            results = quick(descriptor_path=provider.descriptor)
            self.assertEqual(provider.notices_sent, 0)
        for name in ("watch-notices", "watch-coalesced"):
            self.assertEqual(by_name(results)[name]["status"], check.PASS)
            self.assertIn("no change happened while watching", by_name(results)[name]["detail"])
        self.assertIn("--watch-hold 20", by_name(results)["watch-keepalive"]["detail"])

    def test_changes_on_a_timer_are_seen_and_coalesced(self):
        with Running(change_every=0.05, **BRISK) as provider:
            results = check.run(descriptor_path=provider.descriptor, **HELD)
            changes, notices = provider.changes, provider.notices_sent
        self.assertEqual(not_passing(results), {})
        self.assertRegex(by_name(results)["watch-notices"]["detail"], r"\A[2-5] notices, each for")
        self.assertRegex(by_name(results)["watch-coalesced"]["detail"], r"none closer than 2\d\d ms")
        self.assertGreater(changes, notices)

    def test_a_watch_too_short_to_judge_the_keepalive_is_skipped(self):
        with Running() as provider:
            results = check.run(descriptor_path=provider.descriptor, watch_hold=0.2)
        self.assertEqual(not_passing(results), UNHELD)
        self.assertIn("too short to judge", by_name(results)["watch-keepalive"]["detail"])

    def test_the_driven_checks_pass_the_clean_provider(self):
        with Running() as provider:
            moved = driven(provider)
        self.assertEqual(not_passing(moved), {})
        self.assertEqual([(item["requirement"], item["name"]) for item in moved.items], [
            ("PR-084", "watch-change-noticed"), ("PR-083", "watch-trailing-notice"), ("PR-083", "watch-burst-coalesced"),
            ("PR-084", "watch-hover-silent"), ("PR-086", "watch-ends-at-stop"),
        ])
        self.assertIn("completion result", by_name(moved)["watch-ends-at-stop"]["detail"])

    def test_the_stream_as_the_revision_defines_it(self):
        with Running() as provider:
            watch = self.open(provider, request_id="watch-7")
            self.assertTrue(watch.streaming)
            self.assertEqual(watch.response.header("content-type"), "text/event-stream")
            first = watch.first_message()
            meta = {check.META_SUBSCRIPTION: "watch-7"}
            self.assertEqual(first.message, {"jsonrpc": "2.0", "method": check.ACKNOWLEDGED, "params": {
                "_meta": meta, "notifications": {"resourceSubscriptions": [check.CURRENT_URI]}}})
            began = time.monotonic()
            provider.change()
            self.assertIsNotNone(watch.wait_notice(began, 1.0))
            self.assertEqual(watch.messages()[1].message, {
                "jsonrpc": "2.0", "method": check.UPDATED, "params": {"_meta": meta, "uri": check.CURRENT_URI}})
            provider.stop()
            self.assertTrue(watch.wait_end(1.0))
            self.assertEqual(watch.messages()[-1].message, {
                "jsonrpc": "2.0", "id": "watch-7", "result": {"resultType": "complete", "_meta": meta}})
            self.assertTrue(watch.completed)
            self.assertIsNone(watch.failure)

    def test_a_change_alters_the_answer_and_a_hover_only_the_hovered_element(self):
        def answer(provider):
            client = check.Client("127.0.0.1", provider.port, provider.path, provider.token, 2.0)
            document, problems = check.read_document(client.rpc("resources/read", {"uri": check.CURRENT_URI}), check.CURRENT_URI)
            self.assertEqual(problems, [])
            return document

        def without_hover(element):
            return {key: [without_hover(child) for child in value] if key == "children" else value
                    for key, value in element.items() if key != "hovered"}

        with Running() as provider:
            before = answer(provider)
            provider.hover()
            hovered = answer(provider)
            self.assertNotEqual(hovered, before)
            self.assertEqual(without_hover(hovered["root"]), without_hover(before["root"]))
            self.assertEqual(hovered["display"], before["display"])
            provider.change()
            changed = answer(provider)
            self.assertNotEqual(without_hover(changed["root"]), without_hover(before["root"]))
            self.assertNotEqual(changed["display"], before["display"])
            for document in (hovered, changed):
                found, _count = check.check_tree(document["root"])
                self.assertEqual({name for name, problems in found.items() if problems}, set())
            self.assertEqual(provider.reads_served, 3)
            self.assertEqual(provider.most_reads_outstanding, 1)

    def test_a_burst_is_coalesced_and_its_last_change_noticed(self):
        with Running() as provider:
            watch = self.open(provider)
            watch.first_message()
            began = time.monotonic()
            provider.burst(10)
            watch.collect(0.6)
            times = watch.notice_times(began)
            self.assertEqual(len(times), 2)  # The first change at once, the other nine together.
            self.assertGreaterEqual(times[1] - times[0], check.COALESCE - check.COALESCE_TOLERANCE)
            self.assertEqual((provider.changes, provider.notices_sent), (10, 2))

    def test_a_flood_fails_the_driven_burst(self):
        with Running(faults=["watch-flood"]) as provider:
            moved = driven(provider)
        self.assertEqual(not_passing(moved), {"watch-burst-coalesced": check.FAIL})

    def test_the_counters_a_hosts_author_reads(self):
        with Running(delay=0.2) as provider:
            self.assertEqual((provider.watches_open, provider.watches_opened, provider.notices_sent), (0, 0, 0))
            first, second = self.open(provider), self.open(provider)
            first.first_message()
            second.first_message()
            self.assertEqual((provider.watches_open, provider.most_watches_open), (2, 2))
            provider.change()
            self.assertEqual(provider.notices_sent, 2)
            second.close()
            self.assertTrue(self.eventually(lambda: provider.watches_open == 1))
            # Two reads at once, as a host must never make them.
            client = check.Client("127.0.0.1", provider.port, provider.path, provider.token, 2.0)
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda _: client.rpc("resources/read", {"uri": check.CURRENT_URI}), range(2)))
            found = provider.counters()
            self.assertEqual((found["reads_served"], found["most_reads_outstanding"]), (2, 2))
            self.assertEqual((found["watches_opened"], found["most_watches_open"], found["watches_open"]), (2, 2, 1))
            self.assertGreater(found["longest_watch"], 0)
            self.assertNotIn(provider.token, provider.summary())
            self.assertRegex(provider.summary(), r"watches: 2 opened, 2 at most at once, 1 still open")

    def test_a_dropped_watch_ends_with_no_completion(self):
        with Running(drop_watch_after=0.2) as provider:
            watch = self.open(provider)
            self.assertIsNotNone(watch.first_message())
            self.assertTrue(watch.wait_end(2.0))
            self.assertFalse(watch.completed)
            self.assertLess(watch.ended_at - watch.opened_at, 1.0)
            self.assertTrue(self.eventually(lambda: provider.watches_open == 0))
            # The provider still answers, and a host may open the watch again.
            again = self.open(provider)
            self.assertIsNotNone(again.first_message())

    def test_a_chunked_stream_is_read(self):
        framing = check.Framing(True, None)
        self.assertEqual(framing.feed(b"5\r\nhel"), (b"hel", False))
        self.assertEqual(framing.feed(b"lo\r\n3;x=1\r\n: a\r\n0\r\n\r\n"), (b"lo: a", True))
        self.assertEqual(check.Framing(False, 3).feed(b"abcd"), (b"abc", True))
        self.assertEqual(check.Framing(False, None).feed(b"abcd"), (b"abcd", False))

    def test_a_watch_is_opened_on_this_machine_only(self):
        with self.assertRaises(ValueError):
            check.Watch.at("http://192.0.2.2:9/mcp", "secret-token")

    def test_what_a_stream_may_carry(self):
        def message(**fields):
            return check.Event("message", 0.0, dict({"jsonrpc": "2.0"}, **fields))
        meta = {check.META_SUBSCRIPTION: 7}
        ack = message(method=check.ACKNOWLEDGED, params={"_meta": meta, "notifications": {"resourceSubscriptions": [check.CURRENT_URI]}})
        notice = message(method=check.UPDATED, params={"_meta": meta, "uri": check.CURRENT_URI})
        end = message(id=7, result={"resultType": "complete", "_meta": meta})
        comment = check.Event("comment", 0.0)
        self.assertEqual(check.stream_problems([ack, comment, notice, notice, end], 7), ([], 2))
        self.assertEqual(check.acknowledgment_problems(ack, 7), [])
        bad = [
            message(method=check.UPDATED, params={"_meta": meta, "uri": check.CURRENT_URI, "secret field": "secret"}),
            message(method=check.UPDATED, params={"_meta": meta, "uri": "ambient://location/secret"}),
            message(method=check.UPDATED, params={"_meta": {check.META_SUBSCRIPTION: 8}, "uri": check.CURRENT_URI}),
            message(method=check.UPDATED, params={"_meta": dict(meta, secret="secret"), "uri": check.CURRENT_URI}),
            message(method=check.UPDATED, params={"_meta": meta, "uri": check.CURRENT_URI}, secret="secret"),
            message(method=check.UPDATED, params="secret"),
            message(method="notifications/secret"), message(id=8, result={"resultType": "complete"}),
            message(id=7, error={"code": -32603, "message": "secret"}), check.Event("invalid", 0.0), ack,
        ]
        for event in bad:
            problems, _notices = check.stream_problems([ack, event], 7)
            self.assertEqual(len(problems), 1, problems)
            self.assertNotIn("ecret", problems[0])
        for params in (
            {"_meta": meta, "notifications": {"resourceSubscriptions": [check.CURRENT_URI, "ambient://location/secret"]}},
            {"_meta": meta, "notifications": {"resourceSubscriptions": ["ambient://location/secret"]}},
            {"_meta": meta, "notifications": {"resourceSubscriptions": [check.CURRENT_URI], "toolsListChanged": True}},
            {"_meta": {check.META_SUBSCRIPTION: "7"}, "notifications": {"resourceSubscriptions": [check.CURRENT_URI]}},
            {"_meta": meta}, "secret",
        ):
            problems = check.acknowledgment_problems(message(method=check.ACKNOWLEDGED, params=params), 7)
            self.assertEqual(len(problems), 1, problems)
            self.assertNotIn("ecret", problems[0])
        self.assertEqual(check.acknowledgment_problems(
            message(method=check.ACKNOWLEDGED, params={"_meta": meta, "notifications": {
                "resourceSubscriptions": [check.CURRENT_URI], "toolsListChanged": False}}), 7), [])
        for event in (notice, None, check.Event("invalid", 0.0)):
            self.assertEqual(len(check.acknowledgment_problems(event, 7)), 1)

    def test_notices_closer_than_the_limit(self):
        self.assertEqual(check.coalescing_result([])[0], check.PASS)
        self.assertEqual(check.coalescing_result([1.0])[0], check.PASS)
        self.assertEqual(check.coalescing_result([1.0, 1.25, 1.46])[0], check.PASS)
        status, requirement, _name, detail = check.coalescing_result([1.0, 1.1, 1.5, 1.51])
        self.assertEqual((status, requirement), (check.FAIL, "PR-083"))
        self.assertIn("4 notices, 2 of them", detail)

    def test_the_keepalive_is_judged_on_the_longest_silence(self):
        watch = check.Watch("127.0.0.1", 1, "/mcp", "t")
        watch.opened_at = 100.0
        def events(*times):
            return [check.Event("message", 100.0, {})] + [check.Event("comment", at) for at in times]
        self.assertEqual(check.keepalive_result(watch, events(110.0, 120.0), 120.0, False, 20)[0], check.PASS)
        self.assertEqual(check.keepalive_result(watch, events(115.1), 120.0, False, 20)[0], check.PASS)
        self.assertEqual(check.keepalive_result(watch, events(), 120.0, False, 20)[0], check.FAIL)
        self.assertEqual(check.keepalive_result(watch, events(104.0), 120.0, False, 20)[0], check.FAIL)
        self.assertEqual(check.keepalive_result(watch, events(), 102.0, False, 2)[0], check.SKIP)
        self.assertEqual(check.keepalive_result(watch, events(), 102.0, True, 20)[0], check.SKIP)
        self.assertEqual(check.keepalive_result(watch, events(), 100.0, False, 0)[0], check.SKIP)


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
            done = self.run_check(descriptor, "--watch-hold", "0")
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
            done = self.run_check(descriptor, "--json", "--watch-hold", "0")
            process.send_signal(signal.SIGINT)
            process.wait(timeout=10)
        self.assertEqual(done.returncode, 1)
        report = json.loads(done.stdout)
        self.assertEqual(report["protocol"], "0.2.2")
        self.assertEqual(report["summary"]["fail"], 2)
        failed = {(item["requirement"], item["name"]) for item in report["results"] if item["status"] == "FAIL"}
        self.assertEqual(failed, {("PR-053", "hovered-single"), ("PR-059", "ids-unique")})

    def test_changes_on_a_timer_and_the_counters_printed_at_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            process, descriptor = self.start(folder, "--change-every", "0.1", "--keep-alive", "0.1")
            done = self.run_check(descriptor, "--json", "--watch-hold", "0.6")
            process.send_signal(signal.SIGTERM)
            printed = process.stdout.read()
            self.assertEqual(process.wait(timeout=10), 0)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        found = {item["name"]: item for item in json.loads(done.stdout)["results"]}
        self.assertRegex(found["watch-notices"]["detail"], r"\A\d notices?, each for")
        self.assertEqual(found["watch-keepalive"]["status"], "SKIP")
        self.assertRegex(printed, r"watches: 2 opened, 2 at most at once, 0 still open, the longest \d+\.\d s")
        self.assertRegex(printed, r"reads of current: 3 served, 1 at most outstanding at once")
        self.assertRegex(printed, r"notices: [1-9]\d* sent for \d+ changes")

    def test_a_provider_started_without_watch(self):
        with tempfile.TemporaryDirectory() as folder:
            process, descriptor = self.start(folder, "--no-watch")
            done = self.run_check(descriptor)
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=10)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"PASS  PR-081  watch-not-offered")
        self.assertRegex(done.stdout, r"SKIP  PR-080  watch-served +" + NOT_OFFERED)

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
