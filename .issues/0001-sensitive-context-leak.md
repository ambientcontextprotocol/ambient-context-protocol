---
id: 1
title: "Sensitive page content goes out silently with ambient context"
status: proposed
priority: high
labels: [privacy, pii, client]
---

# #1 — Sensitive page content goes out silently with ambient context

When a message is sent from an ACP-aware client (observed in Sirius), the client attaches ambient context from the frontmost app without showing the user what it contains. On 2026.11.17 Andrew sent a Sirius message while an online-store order-confirmation page was frontmost in the browser; the attached context carried his full name, shipping address, order ID and account name. Nothing in the send flow surfaced this, and Andrew noted it is easy to send such context accidentally when he doesn't intend to.

## Problem

- Context capture is implicit: whatever is on screen at send time is eligible, including checkout, banking, health or account pages.
- The user gets no signal that the payload contains personal data (PII) before it leaves the machine.
- The leak is silent, so the user can't correct it after the fact either.

## Options

- **Local PII classifier with a pre-send warning (Andrew's idea).** A small model running on-device scans the captured context for sensitive data such as postal addresses, names, order or account identifiers, phone numbers and payment details, and warns before sending, with options to send anyway, strip the flagged spans, or drop the context. Open question: which local model. Andrew mentioned one by name, but the name was garbled in dictation ("jev"); confirm with him.
- Other directions to weigh: a deterministic redaction pass (regex and pattern rules) as a cheap first layer; per-app or per-domain deny lists (checkout and account pages excluded by default); and a visible context preview or chip the user can inspect before sending.

## Acceptance

Sending with a page like an order confirmation frontmost either warns the user before send or excludes the sensitive fields, and no PII leaves the machine without an explicit choice.
