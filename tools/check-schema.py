#!/usr/bin/env python3
"""Check schema/current-0.2.1.json against the specification's own examples.

Every `current` answer shown in docs/spec and README.md must validate, and
a set of wrong answers, a 0.1 answer among them, must not. The examples
must include answers with `display` and without it.

Needs the `jsonschema` package: python3 -m pip install jsonschema
Usage: python3 tools/check-schema.py
"""
import copy
import json
import re
import sys

from jsonschema import Draft202012Validator

schema = json.load(open("schema/current-0.2.1.json"))
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema)

examples = []
for path in ["README.md", "docs/spec/overview.md", "docs/spec/elements.md", "docs/rfcs/0005-display-and-favicon.md"]:
    for block in re.findall(r"```json\n(.*?)```", open(path).read(), re.S):
        try:
            value = json.loads(block)
        except ValueError:
            continue  # an example shortened with an ellipsis
        if isinstance(value, dict) and "root" in value:
            examples.append((path, value))

failures = 0
for path, value in examples:
    errors = list(validator.iter_errors(value))
    print(("ok      " if not errors else "FAILED  ") + "valid example in " + path)
    for error in errors:
        failures += 1
        print("        " + error.message[:120])

good = examples[0][1]


def changed(edit):
    value = copy.deepcopy(good)
    edit(value)
    return value


def first_child(value):
    return value["root"]["children"][0]


wrong = {
    "a 0.1 answer": {
        "app": {"id": "org.example.editor", "name": "Editor"},
        "instance": "k3f9x2",
        "focus": ["sel-23"],
        "items": [{"id": "doc-1", "type": "document", "title": "draft.md"}],
    },
    "protocol 0.1": changed(lambda v: v.update(protocol="0.1")),
    "an extra field beside root": changed(lambda v: v.update(app={"id": "x"})),
    "a root that is not an Application": changed(lambda v: v["root"].update(role="Window")),
    "an Application below the root": changed(lambda v: first_child(v).update(role="Application")),
    "a role outside the thirteen": changed(lambda v: first_child(v).update(role="Button")),
    "an element with no id": changed(lambda v: first_child(v).pop("id")),
    "an id with a slash": changed(lambda v: first_child(v).update(id="a/b")),
    "an empty children list": changed(lambda v: first_child(v).update(children=[])),
    "focused sent as false": changed(lambda v: first_child(v).update(focused=False)),
    "a text block with no text": changed(lambda v: first_child(v).update(content=[{"type": "text"}])),
    "protocol 0.2.0": changed(lambda v: v.update(protocol="0.2.0")),
    "a display that is a string": changed(lambda v: v.update(display="draft.md")),
    "a display title that is a number": changed(lambda v: v.update(display={"title": 3})),
    "a display detail over two lines": changed(lambda v: v.update(display={"title": "draft.md", "detail": "lines\n12"})),
    "a display title of 81 characters": changed(lambda v: v.update(display={"title": "x" * 81})),
}
for name, value in wrong.items():
    refused = not validator.is_valid(value)
    print(("ok      " if refused else "FAILED  ") + "refused: " + name)
    failures += 0 if refused else 1

right = {
    "an answer with no display": changed(lambda v: v.pop("display", None)),
    "a display with a title and a detail": changed(lambda v: v.update(display={"title": "draft.md", "detail": "lines 12–18"})),
    "a display with a title only": changed(lambda v: v.update(display={"title": "draft.md"})),
    "an empty display": changed(lambda v: v.update(display={})),
}
for name, value in right.items():
    accepted = validator.is_valid(value)
    print(("ok      " if accepted else "FAILED  ") + "accepted: " + name)
    failures += 0 if accepted else 1

with_display = [value for _path, value in examples if "display" in value]
if not examples or not with_display or len(with_display) == len(examples):
    failures += 1
    print("FAILED  the examples must include answers with and without display")
sys.exit(1 if failures else 0)
