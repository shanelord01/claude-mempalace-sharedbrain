/** One coordination event as the mod keeps it: an excerpt, never the full body. */
export type InboxItem = {
  id: string
  type: string
  status: string
  from: string
  to: string
  created: string
  excerpt: string
  /** Requirements the event names (metadata.requires or a "Requires:" line). */
  requires: string[]
  /** Requirements this machine cannot meet, from its capability probe. */
  unmet: string[]
  /** The thread it belongs to: its correlation id, or its own id when it has none. */
  thread?: string
  /** What the bridge may do with it (docs/bridge.md): carry it out, or only report it. */
  level?: 'act' | 'read'
  /** The event's correlation id, when it has one (act level needs it). */
  correlation?: string
  /** This machine's own check of the event's signature; never what the sender claimed. */
  sig?: SigCheck
}

/** The result of verifying an event's signature on this machine (hooks/lib/sb_sign.py). */
export type SigCheck = { ok: boolean; reason: string; key: string }

/** What the mod last learned about this session's place on the hub. */
export type HubStatus = {
  identity: string
  server: string
  cursor: string
  isListening: boolean
  openTasks: InboxItem[]
  checkedAt: number
  error: string
  /** Why the last check failed: a reply too large to read, a hub that did not answer, a connection not up yet, or an error from the hub. */
  cause?: 'too-large' | 'unreadable' | 'slow' | 'unreachable' | 'not-connected' | 'error'
  /** The last check failed and the mod tries again with the next prompt. */
  isRetrying?: boolean
}

/** What the last prompt handed the model, held until the conversation shows it arrived. */
export type Delivery = {
  /** A unique line in the delivered context; finding it in the conversation confirms delivery. */
  marker: string
  /** Inbox cursor to record once delivered ('' when the sweep moved nothing). */
  cursor: string
  /** Watch cursor to record once the mail below is delivered. */
  watchCursor: string
  mail: InboxItem[]
  /** The identity the delivery was for. */
  identity?: string
  /** Broadcast closures it reported (task ids): dropped from the store once delivered. */
  closures?: string[]
}

declare module 'claude-code' {
  interface PluginState {
    'mempalace-sharedbrain': {
      hub: HubStatus | null
      mail: InboxItem[]
      pending: Delivery | null
      watchSeen: string
      server: string
      isPaneOpen: boolean
      peersRelevant: boolean
    }
  }
}
