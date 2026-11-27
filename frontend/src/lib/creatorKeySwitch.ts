// One browser manages one creator page. A working key for a different page
// must not quietly take the place of the one already here.

/** A key is "<handle>.<secret>": the page it opens is the part before the ".". */
export function keyHandle(key: string): string {
  return key.split('.')[0]
}

/** What the server said just now about the key this browser already holds.
 * 'unknown': it could not be asked, for example when offline. */
export type StoredKeyCheck = 'works' | 'dead' | 'unknown'

/** Whether the stored key is for another page than the new one. A replaced
 * link for the same page is not another page. */
export function isOtherPage(stored: string | null, fresh: string): boolean {
  return stored !== null && keyHandle(stored) !== keyHandle(fresh)
}

/** Whether to ask before an accepted new key replaces the stored one. Only a
 * key known to be dead is given up without asking. */
export function mustAskBeforeSwitching(
  stored: string | null,
  fresh: string,
  check: StoredKeyCheck,
): boolean {
  return isOtherPage(stored, fresh) && check !== 'dead'
}
