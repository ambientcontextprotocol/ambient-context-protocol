# The RFC process

Last updated: `2026.11.10`

> How the Ambient Context Protocol changes: what needs an RFC, how one is written, reviewed and decided, and how an accepted RFC becomes a new version of the specification.

Status: proposed. This process is itself not yet adopted; see the note at the end.

## 1. Three paths for a change

| Path | Use it for | Examples |
|---|---|---|
| Pull request alone | Anything that does not change what a conforming provider or host must do | Typos and clearer wording, examples, fixes to an SDK that bring it in line with the specification, tests, tooling |
| RFC | Anything that changes behavior between a provider and a host, or what either must do | A new field or operation, a changed meaning, a discovery or trust rule, a limit, the versioning rules, this process |
| Security report | A weakness that could expose a user's context | Reported privately first; see [CONTRIBUTING](../../CONTRIBUTING.md#security) |

When in doubt, ask whether an implementation written before the change would still be correct after it. If not, it needs an RFC.

## 2. Life of an RFC

| Step | What happens | Who |
|---|---|---|
| 1. Discuss | Open an RFC candidate: an issue that states a need and the evidence for it, with no design. See [section 2.1](#21-rfc-candidates). Optional, and recommended before writing | Anyone |
| 2. Draft | Copy [the template](0000-template.md) to `docs/rfcs/NNNN-short-title.md`, taking the next unused number in [the index](index.md). Open a pull request that adds the file with status Draft and a row in the index | The author |
| 3. Review | Discussion happens on the pull request. The author keeps the RFC current, so that the document, not the comment history, states the proposal | Anyone |
| 4. Decide | A maintainer records the outcome in section 10 of the RFC, sets its status and fills "Decided" with the date. An accepted or provisional RFC is merged. A declined one is merged too, with its reason, so the number and the reasoning are kept | A maintainer |
| 5. Implement | A separate pull request changes the specification, the version, the changelog, the SDKs and the conformance check, and cites the RFC. When a released version contains the change, the RFC's status becomes Released and its "Released in" field names that version | The author or a maintainer |

Numbers are four digits, given in order and never reused. Reserving a number means opening the draft pull request.

### 2.1 RFC candidates

An RFC candidate, a candidate for short, is an issue opened from the "RFC candidate" form. It records a need, what was observed, who it touches and the questions an RFC would have to answer. It proposes no design, so it can be written the moment a need is seen.

Anyone may write an RFC for a candidate; no acceptance is needed first, and the decision is made on the RFC. A maintainer closes a candidate in one of four ways, and its label says which:

| Label | Outcome |
|---|---|
| `rfc` | An RFC is opened and linked from the candidate. The candidate closes when the RFC is decided |
| `no-rfc` | It changes no behavior between a provider and a host, so a pull request alone settles it |
| `host` | It is a host's own business and not the protocol's. It moves to that host's tracker |
| `declined` | Not pursued, with the reason |

Until then it carries `rfc-candidate`. A bug in a package or in the conformance check is an ordinary issue and needs no form.

## 3. Statuses

| Status | Meaning |
|---|---|
| Draft | Under review. Nothing is adopted |
| Provisional | Chosen for a bounded trial. The RFC records the scope, the owner, how the trial will be judged and when it is reviewed. Implementations mark the feature experimental |
| Accepted | Adopted within the scope the RFC states. Not yet necessarily in the specification |
| Released | Accepted, implemented, and present in a released version of the specification, which the RFC names |
| Deferred | Paused, with the reason and the condition for returning to it |
| Withdrawn | Withdrawn by its author |
| Rejected | Declined, with reasons |
| Superseded | Replaced by a later accepted RFC, which it links |

An accepted RFC is not edited to change its meaning. A substantive change is a new RFC that supersedes or amends it. Editorial corrections are made directly. An RFC carries two dates, "Created" and "Decided", and no "Last updated" line: a draft's history is in git, and a decided RFC does not change.

## 4. What an RFC must contain

Beyond the template's sections, an RFC is complete enough to decide when it states:

1. *The exact change to the specification:* which sections, and the new normative text or a faithful description of it.
2. *Compatibility:* whether an existing provider or host stops working, and so which part of the version changes (section 6).
3. *Privacy and security:* what new information leaves an app, who can ask for it, and what a hostile local program could do with the change.
4. *Conformance:* how an outside check can tell a correct implementation from an incorrect one. A requirement that cannot be checked is marked as such.
5. *Requirements:* the entries in [the product model](../pm.md) it adds, changes or removes.
6. *Implementation evidence,* before Accepted becomes Released: at least one provider and one host that implement it and pass the conformance check.

Gaps are acceptable in a Draft and are listed under open questions. An RFC does not invent settled answers.

## 5. Who decides

While the protocol is before version 1.0, the maintainers listed in [CONTRIBUTING](../../CONTRIBUTING.md#maintainers) decide, and one maintainer's recorded decision is enough. The decision names who made it, on which revision of the RFC, and why.

From version 1.0 this section must be revised by RFC to say how decisions are made when there is more than one implementer with a stake: at the least, a stated comment period before a decision and a record of objections.

Discussion that happens elsewhere, in a private thread or a call, does not count until its substance is written into the RFC or the pull request. The RFC is the record.

## 6. How an accepted RFC changes the version

The protocol version has three parts, `major.minor.patch`.

| Change | Before 1.0 | From 1.0 |
|---|---|---|
| Breaks an existing implementation | minor: `0.1.0` to `0.2.0` | major |
| Adds something a receiver may ignore | patch: `0.2.0` to `0.2.1` | minor |
| Clarifies with no change in behavior | no version change; changelog entry only | patch |

Rules:

1. One version of the specification may contain several RFCs. The changelog entry for a version lists every RFC in it.
2. The specification is the contract. An RFC explains why; once it is released, the specification's text governs, and a conflict between them is a defect in the specification to be fixed by pull request.
3. A provisional feature is carried as experimental and does not change the version until it is accepted.
4. The specification today writes versions with two parts (`0.1`). Moving to three is part of RFC-0001.

## 7. The index

[`index.md`](index.md) lists every RFC that has a number, with its status. It is updated in the same pull request that changes a status.

## 8. Adopting this process

This document, the template, the index and CONTRIBUTING took effect on `2026.11.10`, when the maintainer approved them. RFC-0001 and RFC-0002 were the first uses of the process and were accepted the same day.

Adapted from the RFC procedure used in the maintainers' World Model repository, with pull-request review and versioning rules added for a public protocol.
