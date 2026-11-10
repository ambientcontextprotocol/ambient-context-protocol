// The Ambient Context Protocol's types, draft 0.1, and the interface an
// app implements to be a provider: `ContextProvider` to say what the user
// has open and selected, with `locate` as well if it can also say where
// an item is on screen.

/** One block of an item's content, in MCP's `ContentBlock` form. */
export type ContextContent =
  | { type: "text"; text: string }
  | { type: "image"; data: string; mimeType: string }
  | { type: "resource_link"; uri: string; name: string };

/** Builders for the content blocks, one per case. */
export const ContextContent = {
  text(text: string): ContextContent {
    return { type: "text", text };
  },
  /** `data` is the image's bytes; they are sent as base64. */
  image(data: Uint8Array, mimeType: string): ContextContent {
    return { type: "image", data: Buffer.from(data).toString("base64"), mimeType };
  },
  resourceLink(uri: string, name: string): ContextContent {
    return { type: "resource_link", uri, name };
  },
};

/** A free-form value for an item's `payload`. */
export type ContextValue = string | number | boolean | ContextValue[] | { [key: string]: ContextValue };

/** One thing the user has open or selected. */
export interface ContextItem {
  id: string;
  type: string;
  title: string;
  content?: ContextContent[];
  url?: string;
  parent?: string;
  locatable?: boolean;
  payload?: { [key: string]: ContextValue };
}

/**
 * The provider's answer to `current`, before the server adds the app and
 * the instance.
 */
export interface ContextCurrent {
  focus?: string[];
  items?: ContextItem[];
}

/**
 * A rectangle in global display coordinates: points, origin at the top
 * left of the primary display, y increasing downward.
 */
export interface ContextRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export type ContextLocationState = "visible" | "offscreen" | "gone";
export type ContextLocationEdge = "left" | "right" | "top" | "bottom";

/** Where an item is on screen, at one moment. */
export interface ContextLocation {
  id: string;
  state: ContextLocationState;
  rects?: ContextRect[];
  window?: number;
  avoid?: ContextRect;
  edge?: ContextLocationEdge;
}

export const ContextLocation = {
  gone(id: string): ContextLocation {
    return { id, state: "gone" };
  },
};

/**
 * What an app implements to be a provider. Each function may answer
 * directly or with a promise. Further optional functions may be added
 * here; a provider that leaves one out does not offer what it serves.
 */
export interface ContextProvider {
  /** What the user has open and in focus, from state already in memory. */
  current(): ContextCurrent | Promise<ContextCurrent>;

  /**
   * Where the item is, or nothing for an id this run never issued. An
   * item that was issued and no longer exists is a location whose state
   * is `gone`. Optional: a provider without it offers no location
   * resource, and a host places its own interface by default.
   */
  locate?(id: string): ContextLocation | null | undefined | Promise<ContextLocation | null | undefined>;
}

/** A provider that can also say where an item is on screen. */
export type ContextLocator = ContextProvider & Required<Pick<ContextProvider, "locate">>;
