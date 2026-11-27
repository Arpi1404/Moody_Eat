// The words a quest's creator writes: an intro and a note on each stop.
// The limits mirror backend/models.py: change one, change both.

export const CREATOR_NOTE_MAX = 200
export const CREATOR_INTRO_MAX = 300

// Control characters (newlines and tabs among them), line separators, and the
// marks that make text display in a different order from how it was typed.
const UNSAFE_RE = /[\p{Cc}\u2028\u2029\u202a-\u202e\u2066-\u2069]/gu

/** One trimmed line, as it will be saved and counted. */
export function tidyText(text: string): string {
  return text.replace(UNSAFE_RE, ' ').replace(/\s+/g, ' ').trim()
}

// Anything a chat app would turn into a tappable link: addresses with a scheme
// or "www.", and bare domains under common endings.
const LINK_RE =
  /\b(?:https?:\/\/|www\.)\S+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|in|io|co|me|ly|gg|to|ai|app|dev|xyz|info|biz|shop|store|link|site|online|club|top|live)\b(?:\/\S*)?/gi

/** For text pasted into chat apps. React never renders links from text, but
 * WhatsApp makes one out of anything shaped like an address. */
export function withoutLinks(text: string): string {
  return text.replace(LINK_RE, '(link removed)')
}
