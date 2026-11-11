# Contributing

Last updated: `2026.11.10`

> How to propose a change to the Ambient Context Protocol, its specification or its packages.

Status: proposed, with the RFC process it refers to. Three items marked "to be decided" need a maintainer's answer before this repository is opened to others.

## What is here

| Path | What it is |
|---|---|
| `docs/spec/` | The specification. The contract between a provider and a host |
| `docs/pm.md` | The product model: the features and requirements the specification must satisfy |
| `docs/rfcs/` | Proposals to change the protocol, and the record of what was decided |
| `sdk/swift`, `sdk/typescript` | Packages that make an app a provider |

## Which path to take

1. *A fix that does not change behavior:* wording, an example, a bug in a package, a test. Open a pull request.
2. *A change to what a provider or host must do:* write an RFC. The steps are in [the RFC process](docs/rfcs/README.md). A candidate first is welcome and often saves work: an issue that states the need and the evidence, with no design ([candidates](docs/rfcs/README.md#21-candidates)).
3. *A security problem:* do not open a public issue. See [Security](#security).

If you are unsure which applies, open an issue and ask.

## Pull requests

- One change per pull request, with a description of what changes and why.
- A change to a package comes with a test. Run `swift test` in `sdk/swift` and `npm test` in `sdk/typescript` before opening it.
- A change to one package that affects behavior on the wire is made in the other in the same pull request, or the pull request says why not. The two packages must behave identically.
- A change to the specification's behavior cites the accepted RFC it implements, bumps the version as the process describes, and adds a changelog entry.
- Commit subjects follow `type(scope): what changed`, for example `fix(sdk): refuse a request with an Origin header`. Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`.
- Markdown prose is not hard-wrapped: one paragraph is one line.

## Implementing the protocol

You do not need permission to implement a provider or a host, in any language. If you do:

- Say which version of the specification you implement.
- Run the conformance check against it once that check is published in this repository. Until then, the packages' test suites are the reference for behavior.
- Tell us where the specification was unclear. An ambiguity that two implementers resolve differently is a defect, and a pull request or an issue for it is one of the most useful contributions.

## Maintainers

Maintainers decide RFCs and merge pull requests.

- Andrew Jones

## Security

A provider hands a user's open documents and selected text to whoever is allowed to ask. A weakness here is serious. Report one privately, with enough detail to reproduce it, and allow time for a fix before publishing.

*To be decided:* the private address or channel for reports.

## To be decided before opening the repository

1. *License.* The repository has no license file. Contributions cannot be accepted from others until the license for the specification and for the packages is chosen.
2. *Security contact.* See above.
3. *Conduct.* Whether to adopt a code of conduct, and which.
