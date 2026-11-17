// The package's public interface. `ContextServer` is the whole of it for
// an app with no server of its own. `ContextResponder` and
// `ContextDescriptor` are for an app that answers on a listener it already
// has (RFC-0002). `ContextHTTP`, the request parser under them, is in
// `server.ts`, open to the package's tests.

export { ContextContent, ContextLocation, contextRoles } from "./provider.ts";
export type {
  ContextDisplay,
  ContextElement,
  ContextLocationEdge,
  ContextLocationState,
  ContextLocator,
  ContextProvider,
  ContextRect,
  ContextRole,
  ContextValue,
} from "./provider.ts";
export { ContextTree } from "./tree.ts";
export type { ContextIssue } from "./tree.ts";
export { ContextDescriptor, ContextResponder, ContextServer } from "./server.ts";
export type {
  ContextApp,
  ContextHTTPRequest,
  ContextHTTPResponse,
  ContextResponderOptions,
  ContextServerOptions,
} from "./server.ts";
