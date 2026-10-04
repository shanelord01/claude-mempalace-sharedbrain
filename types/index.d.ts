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
}

/** What the mod last learned about this session's place on the hub. */
export type HubStatus = {
  identity: string
  server: string
  cursor: string
  isListening: boolean
  openTasks: InboxItem[]
  checkedAt: number
  error: string
  /** The last check failed and the mod tries again with the next prompt. */
  isRetrying?: boolean
}

declare module 'claude-code' {
  interface PluginState {
    'mempalace-sharedbrain': {
      hub: HubStatus | null
      mail: InboxItem[]
    }
  }
}
