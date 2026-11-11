import { contextRoles } from "./provider.ts";
import type { ContextElement } from "./provider.ts";

// What can be wrong with a tree that could not be wrong with a list, and
// can be told from the tree alone (RFC-0001 section 7, RFC-0003). The
// server runs this on a provider's answer so an app's author hears of a
// mistake from the app, not from a host that reads it oddly.

export interface ContextIssue {
  /**
   * An `error` is an answer a host may refuse or misread. A `warning` is
   * one it will read, though perhaps not as meant: a role outside the
   * language is read as `Group`.
   */
  severity: "error" | "warning";
  /** The element's `id`, as far as it has one. */
  element: string;
  message: string;
}

const idPattern = /^[A-Za-z0-9_-]{1,128}$/;
const roles: ReadonlySet<string> = new Set(contextRoles);

export const ContextTree = {
  /** Letters, digits, hyphens and underscores, as the protocol allows. */
  isElementID(id: unknown): id is string {
    return typeof id === "string" && idPattern.test(id);
  },

  /**
   * Everything wrong with the tree under `root`, in the order met; empty
   * for a tree with nothing to report.
   */
  check(root: ContextElement): ContextIssue[] {
    const issues: ContextIssue[] = [];
    const seen = new Set<string>();
    let hovered = 0;
    const note = (severity: ContextIssue["severity"], element: ContextElement, message: string): void => {
      issues.push({ severity, element: typeof element.id === "string" ? element.id : "", message });
    };

    if (root.role !== "Application") note("error", root, `the root's role is '${String(root.role)}', not 'Application'`);

    // `onPath` is whether the parent lies on the focused path; the root
    // does, whether or not it is marked.
    const visit = (element: ContextElement, onPath: boolean, depth: number): void => {
      if (!ContextTree.isElementID(element.id)) {
        note("error", element, "the id is not 1 to 128 letters, digits, hyphens or underscores");
      } else if (seen.has(element.id)) {
        note("error", element, "the id is used by more than one element");
      } else {
        seen.add(element.id);
      }
      if (!roles.has(element.role)) {
        note("warning", element, `the role '${String(element.role)}' is not in the role language and will be read as 'Group'`);
      } else if (element.role === "Application" && depth > 0) {
        note("error", element, "only the root is an 'Application'");
      }
      if (element.focused === true && !onPath) {
        note("error", element, "focused, but an element between it and the root is not: the focused path has a gap");
      }
      if (element.hovered === true && ++hovered === 2) {
        note("error", element, "hovered, and so is an earlier element: at most one element is hovered");
      }
      const children = element.children ?? [];
      const focused = children.filter((child) => child.focused === true);
      if (focused.length > 1 && focused[1]) {
        note("error", focused[1], "focused, and so is an earlier element beside it: the focused path forks");
      }
      const here = depth === 0 || (onPath && element.focused === true);
      for (const child of children) visit(child, here, depth + 1);
    };
    visit(root, true, 0);
    return issues;
  },
};
