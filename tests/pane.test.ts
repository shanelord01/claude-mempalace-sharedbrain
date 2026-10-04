// The /mempalace pane, drawn by the engine's own element tables on each surface.
import type { On } from 'claude-code'
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

describe('opening and closing', () => {
  function recordPanes(on: On) {
    const calls: Array<{ op: string; args: Record<string, unknown> }> = []
    on('ui.open', async (_$, e) => {
      calls.push({ op: 'open', args: { ...e } })
      return { value: { isPlaced: true as const } }
    })
    on('ui.close', async (_$, e) => {
      calls.push({ op: 'close', args: { ...e } })
      return { value: undefined }
    })
    return calls
  }

  test('/mempalace toggles, open and close say which, Escape closes', async ($, on) => {
    const calls = recordPanes(on)
    const first = await $.command.run({ command: 'mempalace', args: '' } as never)
    expect(JSON.stringify(first)).toContain('opened')
    expect(calls[0]).toEqual({ op: 'open', args: expect.objectContaining({ id: 'mempalace-hub', closeOnEscape: true, focus: true }) })
    const second = await $.command.run({ command: 'mempalace', args: '' } as never)
    expect(JSON.stringify(second)).toContain('closed')
    expect(calls[1]?.op).toBe('close')
    await $.command.run({ command: 'mempalace', args: 'close' } as never)
    expect(calls[2]?.op).toBe('close')
    await $.command.run({ command: 'mempalace', args: 'open' } as never)
    await $.command.run({ command: 'mempalace', args: 'open' } as never)
    expect(calls.slice(3).map(c => c.op)).toEqual(['open', 'open'])
  })

  test('the Close button closes the pane', async ($, on) => {
    const calls = recordPanes(on)
    const ui = await $.ui.mount({ plugin: 'mempalace-sharedbrain', surface: 'terminal', component: 'Pane', props: PANE_PROPS, requestId: 'mempalace-hub' } as never)
    await ui.press({ key: 'close' } as never)
    expect(calls.map(c => c.op)).toContain('close')
  })
})
