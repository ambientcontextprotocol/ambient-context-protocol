// The package's public interface. The layers under `ContextServer` are
// in `server.ts`, open to the package's tests.

export { ContextContent, ContextLocation } from "./provider.ts";
export type {
  ContextCurrent,
  ContextItem,
  ContextLocationEdge,
  ContextLocationState,
  ContextLocator,
  ContextProvider,
  ContextRect,
  ContextValue,
} from "./provider.ts";
export { ContextDescriptor, ContextServer } from "./server.ts";
export type { ContextApp, ContextServerOptions } from "./server.ts";
