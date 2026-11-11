# Ambient Context Protocol

Version `0.1` · Draft of `2026.11.09` · Not stable. Everything here may change, every name is a placeholder, and nothing has shipped.

> The Ambient Context Protocol lets a desktop app tell an ambient agent what the user is looking at, so that "this" means something when the user asks a question. It also lets the agent's interface appear beside the thing in question. An app answers two questions: what is open and selected, and where a listed thing is on screen. Version 0.1 is defined as an extension to the Model Context Protocol (MCP): both answers are MCP resources.

## Contents

1. [The problem](overview.md#1-the-problem)
2. [An example](overview.md#2-an-example)
3. [Roles and principles](overview.md#3-roles-and-principles)
4. [Operations](operations.md#4-operations)
   - [4.1 — current](operations.md#41--current)
   - [4.2 — locate](operations.md#42--locate)
5. [Items](elements.md#5-items)
6. [Locations](locations.md#6-locations)
7. [The MCP binding](binding.md#7-the-mcp-binding)
   - [7.1 — The server](binding.md#71--the-server)
   - [7.2 — Declaring the extension](binding.md#72--declaring-the-extension)
   - [7.3 — The two resources](binding.md#73--the-two-resources)
   - [7.4 — Errors and refusals](binding.md#74--errors-and-refusals)
   - [7.5 — An optional tool](binding.md#75--an-optional-tool)
   - [7.6 — Older MCP clients](binding.md#76--older-mcp-clients)
8. [Discovery](discovery.md#8-discovery)
9. [Rules](security.md#9-rules)
   - [9.1 — For providers](security.md#91--for-providers)
   - [9.2 — For hosts](security.md#92--for-hosts)
10. [Versioning](versioning.md#10-versioning)
11. [Implementing a provider](binding.md#11-implementing-a-provider)
12. [Not in version 0.1](versioning.md#12-not-in-version-01)
13. [Open questions](versioning.md#13-open-questions)
14. [MCP details this draft relies on](binding.md#14-mcp-details-this-draft-relies-on)

[Changelog](versioning.md#changelog)
