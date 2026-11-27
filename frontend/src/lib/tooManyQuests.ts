// What a person sees when a limit on new quests is reached. There are two, one
// per minute and one per hour, and the server says how long is left.

/** The message for a 429, given the server's `retry_after_seconds`. */
export function tooManyQuestsMessage(retryAfterSeconds: unknown): string {
  if (typeof retryAfterSeconds === 'number' && retryAfterSeconds > 60) {
    const minutes = Math.ceil(retryAfterSeconds / 60)
    return `That's a lot of quests for one hour. Try again in about ${minutes} minutes.`
  }
  return "That's a lot of quests at once. Wait a minute, then try again."
}

export class TooManyQuestsError extends Error {
  constructor(retryAfterSeconds: unknown) {
    super(tooManyQuestsMessage(retryAfterSeconds))
    this.name = 'TooManyQuestsError'
  }
}
