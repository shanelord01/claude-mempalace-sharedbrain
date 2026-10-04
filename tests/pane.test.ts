// The /mempalace pane, drawn by the engine's own element tables on each surface.
import { describe, expect, test } from 'claude-code/testing'

const PANE_PROPS = { title: 'MemPalace shared brain', isFocused: false, bodyColumns: 80, placement: 'dock' } as never

describe('pane', () => {
  for (const surface of ['terminal', 'desktop'] as const) {
    test(`draws before any hub check (${surface})`, async $ => {
      const ui = await $.ui.mount({ plugin: 'mempalace-sharedbrain', surface, component: 'Pane', props: PANE_PROPS, requestId: 'mempalace-hub' } as never)
      const found = await ui.findAll({ type: 'Text' })
      expect(found.length).toBeGreaterThan(0)
      expect(await ui.find({ text: /No hub check yet/ })).toBeDefined()
    })
  }
})
