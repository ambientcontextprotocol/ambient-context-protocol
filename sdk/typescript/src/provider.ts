// The Ambient Context Protocol's types, version 0.2.4 (RFC-0001, the
// element model; RFC-0003, the hovered state; RFC-0005, display), and the interface an app
// implements to be a provider: `ContextProvider` to say what the user has
// open and selected, with `locate` as well if it can also say where an
// element is on screen.

/** One block of an element's content, in MCP's `ContentBlock` form. */
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

/** A free-form value for an element's `attributes`. */
export type ContextValue = string | number | boolean | ContextValue[] | { [key: string]: ContextValue };

/**
 * The role language: how a thing is shown. Thirteen words, spelled as
 * here. What the thing is, in the app's own word, goes in `subrole`.
 */
export const contextRoles = [
  "Application", "Window",
  "Group", "List", "Table",
  "Row", "Cell",
  "Text", "Heading", "Link",
  "Image", "Page",
  "Document",
] as const;
export type ContextRole = (typeof contextRoles)[number];

/**
 * One thing the user has open, and what is inside it. A provider answers
 * with one tree of these, rooted at an `Application`.
 */
export interface ContextElement {
  /**
   * Letters, digits, hyphens and underscores. Unique within one answer
   * and stable for one run. Names one appearance: the same thing shown
   * twice is two elements.
   */
  id: string;
  role: ContextRole;
  /** The app's own word for what the thing is. */
  subrole?: string;
  /** One line a person could read. */
  title?: string;
  content?: ContextContent[];
  url?: string;
  /** The user selected this. Absent means false. */
  selected?: boolean;
  /**
   * The keyboard or cursor is here. Set on every element of the path
   * from the root's children down to the user's position, with no gaps.
   * Absent means false.
   */
  focused?: boolean;
  /**
   * The pointer is over this element now. On at most one element: the
   * innermost reported one under the pointer, never its ancestors.
   * Absent means false.
   */
  hovered?: boolean;
  /** Drawn on screen now. Absent means the parent's value; the root is visible. */
  visible?: boolean;
  /** The elements inside this one, in the app's order. */
  children?: ContextElement[];
  /**
   * Anything else, by name. Two names are reserved: `author`, who wrote
   * the thing, as a string; and `related`, a list of links that are not
   * containment, each with a relation name and another element's `id`
   * or an address.
   */
  attributes?: { [key: string]: ContextValue };
}

/**
 * The app's own words for what an answer holds, for the line a host shows
 * the user: `release-runbook.md · lines 12–18`. Optional. A host that gets
 * none words the line itself from the tree.
 *
 * It labels the answer it is sent with: it names nothing the tree does
 * not hold. Each string is sent on one line of at most 80 characters, and
 * nothing is sent without a title, since a host uses `display` only when
 * it has one. The picture a host draws beside it is not sent; it is a
 * favicon file the app ships, which the host finds itself.
 */
export interface ContextDisplay {
  /** What is open: the document, the view, the thread. */
  title?: string;
  /** What is selected or in focus within it: `lines 12–18`, `3 tasks`. */
  detail?: string;
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

/** Where an element is on screen, at one moment. */
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
  /**
   * What the user has open, as one tree rooted at an `Application`, from
   * state already in memory. The server adds the protocol version and the
   * instance.
   */
  current(): ContextElement | Promise<ContextElement>;

  /**
   * The app's own words for what `current()` holds, or nothing to let the
   * host word it. Called straight after `current()`. Optional.
   */
  display?(): ContextDisplay | null | undefined | Promise<ContextDisplay | null | undefined>;

  /**
   * True when what `current()` holds is likely private to the user or to
   * someone else, so that a host asks the user before sending it on
   * (RFC-0007). Called straight after `current()`. Sent as
   * `"sensitive": true` when it answers exactly `true` and left out
   * otherwise, never sent as `false`. It asks for the user's confirmation
   * and nothing more: leaving out or masking private details in the tree
   * is still this provider's job, not the host's. Optional.
   */
  sensitive?(): boolean | null | undefined | Promise<boolean | null | undefined>;

  /**
   * Where the element is, or nothing for an id this run never issued. An
   * element that was issued and no longer exists is a location whose
   * state is `gone`. Optional: a provider without it offers no location
   * resource, and a host places its own interface by default.
   */
  locate?(id: string): ContextLocation | null | undefined | Promise<ContextLocation | null | undefined>;
}

/** A provider that can also say where an element is on screen. */
export type ContextLocator = ContextProvider & Required<Pick<ContextProvider, "locate">>;
