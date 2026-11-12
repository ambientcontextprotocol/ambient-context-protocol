// The repository's address. This is the single place it lives (task ACP-0013): the generated specification and RFC pages build their links to repository files from it, and so should anything else on the site.
export const repoUrl = 'https://github.com/ambientcontextprotocol/ambient-context-protocol';

// The branch that links to repository files point at.
export const repoBranch = 'master';

/**
 * The address of a file in the repository.
 * @param {string} path Path from the repository root, for example `schema/current-0.2.0.json`.
 * @returns {string}
 */
export function repoFileUrl(path) {
  return `${repoUrl}/blob/${repoBranch}/${path}`;
}
