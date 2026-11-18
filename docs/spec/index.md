# Ambient Context Protocol

Version `0.2.4` · Draft of `2026.11.18` · Not stable. Everything here may change, every name is a placeholder, and nothing has shipped.

> The Ambient Context Protocol lets a desktop app tell an ambient agent what the user is looking at, so that "this" means something when the user asks a question. It also lets the agent's interface appear beside the thing in question. An app answers two questions: what is open and selected, as one tree of elements, and where an element is on screen. It may also say when the first answer changes. Version 0.2.4 is defined as an extension to the Model Context Protocol (MCP): both answers are MCP resources.

The accepted proposals behind each version are in the [RFCs](../rfcs/README.md). Where this specification and an RFC differ, this specification is the contract and the difference is a defect to report.

## Contents

Section numbers run through the whole specification, so "section 8" names the same thing wherever it is cited.

| File | Sections |
|---|---|
| [Overview](overview.md) | [1. The problem](overview.md#1-the-problem) · [2. An example](overview.md#2-an-example) · [3. Roles and principles](overview.md#3-roles-and-principles) |
| [Operations](operations.md) | [4. Operations](operations.md#4-operations): [4.1 current](operations.md#41--current), [4.2 locate](operations.md#42--locate), [4.3 display](operations.md#43--display), [4.4 watch](operations.md#44--watch), [4.5 sensitive](operations.md#45--sensitive) |
| [Elements](elements.md) | [5. Elements](elements.md#5-elements): [5.1 fields](elements.md#51--fields), [5.2 roles](elements.md#52--roles), [5.3 states](elements.md#53--states), [5.4 ids and instances](elements.md#54--ids-and-instances), [5.5 content](elements.md#55--content), [5.6 attributes](elements.md#56--attributes), [5.7 what to report](elements.md#57--what-to-report) |
| [Locations](locations.md) | [6. Locations](locations.md#6-locations) |
| [The MCP binding](binding.md) | [7. The MCP binding](binding.md#7-the-mcp-binding): [7.1 the server](binding.md#71--the-server), [7.2 declaring the extension](binding.md#72--declaring-the-extension), [7.3 the two resources](binding.md#73--the-two-resources), [7.4 errors and refusals](binding.md#74--errors-and-refusals), [7.5 an optional tool](binding.md#75--an-optional-tool), [7.6 older MCP clients](binding.md#76--older-mcp-clients), [7.7 watching](binding.md#77--watching) · [11. Implementing a provider](binding.md#11-implementing-a-provider) · [14. MCP details this draft relies on](binding.md#14-mcp-details-this-draft-relies-on) |
| [Discovery](discovery.md) | [8. Discovery](discovery.md#8-discovery): [8.1 platform profiles](discovery.md#81--platform-profiles), [8.2 the app's favicon](discovery.md#82--the-apps-favicon) |
| [Rules](security.md) | [9. Rules](security.md#9-rules): [9.1 for providers](security.md#91--for-providers), [9.2 for hosts](security.md#92--for-hosts) |
| [Versioning](versioning.md) | [10. Versioning](versioning.md#10-versioning) · [12. Not in version 0.2.4](versioning.md#12-not-in-version-024) · [13. Open questions](versioning.md#13-open-questions) · [Changelog](versioning.md#changelog) |
