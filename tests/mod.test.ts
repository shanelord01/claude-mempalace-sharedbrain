// Run with: claude plugin test .
// The test's `on` hooks sit beneath the mod and stand for the engine: they answer $.process.run (the
// plugin's Python) and $.mcp.call (the hub) from memory.
import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'

import { itemLine, parseCheckIn, requiresOf, sessionsTable, toItem, unmetRequirements } from '../hooks/register'

const ME = 'office-desktop:claude:demo'
const SERVER = 'claude.ai Mempalace'

type Ctx = Record<string, unknown>

function context(over: Ctx = {}): Ctx {
  return {
    identity: ME, diary: 'office-desktop_claude_demo', cursor: 'evt_00', watch: {}, mcp_server: '',
    inbox_limit: 10, sweep: true, wake_types: ['task.request', 'task.reply', 'patch.ready'], wake_limit: 50,
    version: '0.4.0', presence: { enabled: true, wing: 'fleet', room: 'presence', interval_minutes: 30, drawer_id: '' }, capabilities: { python: { present: true, version: '3.14.7' }, 'memory-gb': { present: true, version: '62' } },
    ...over,
  }
}

const TASK_NEEDS_XCODE = {
  id: 'evt_01', type: 'task.request', status: 'open', from_agent: 'mac-mini:claude:app', to_agent: ME,
  created_at: '2026-10-04T00:00:00Z', body: 'Build the iOS app', metadata: { requires: ['xcode>=27'] },
}
const TASK_ACKED = { id: 'evt_02', type: 'task.request', status: 'open', from_agent: 'other', to_agent: '*', body: 'done already' }
const MY_ACK = { id: 'evt_03', type: 'event.ack', from_agent: ME, metadata: { ack_of: 'evt_02' } }

function world(on: On, opts: { ctx?: Ctx; hubDown?: boolean; newMail?: unknown[]; isUp?: () => boolean; meshPeers?: unknown[]; rawReply?: string; presence?: string[] } = {}) {
  const calls: string[][] = []
  const mcp: Array<{ tool: string; args: Record<string, unknown> }> = []
  const beneath: Array<Record<string, unknown>> = []
  mock.env(on, {})
  mock.clock(on)
  on('session.cwd', async () => ({ value: '/tmp/demo/sub' }))
  on('session.root', async () => ({ value: '/tmp/demo' }))
  for (const noop of ['ui.log', 'ui.status', 'ui.toast', 'ui.invalidate'] as const) on(noop, async () => ({ value: undefined }))
  // Stand-ins for the plugin's command hooks: record what reached them, add their own context.
  on('classic.SessionStart', async (_$: unknown, e: Record<string, unknown>) => {
    beneath.push(e)
    return { additionalContext: ['COMMAND-HOOK BLOCK'] }
  })
  on('classic.UserPromptSubmit', async (_$: unknown, e: Record<string, unknown>) => {
    beneath.push(e)
    return {}
  })
  on('classic.Stop', async () => ({}))
  on('command.describe', async (_$, e) => ({ description: e.description, isHidden: e.isHidden }))
  // The conversation as sent to the model: the test decides what reached it.
  const conversation: string[] = []
  on('session.messages', async () => ({ value: [{ role: 'user', content: [{ type: 'text', text: conversation.join('\n') }] }] }))
  on('process.run', async (_$: unknown, e: { argv: readonly string[] }) => {
    const args = e.argv.slice(2)
    calls.push([...args])
    if (e.argv.includes('--cwd')) expect(e.argv[e.argv.indexOf('--cwd') + 1]).toBe('/tmp/demo')
    if (args[0] === 'mod-context') return { value: { exitCode: 0, stdout: JSON.stringify(opts.ctx ?? context()), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    return { value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('mcp.call', async (_$: unknown, e: { server: string; tool: string; args: Record<string, unknown> }) => {
    mcp.push({ tool: e.tool, args: e.args })
    if (opts.rawReply !== undefined) return { value: { content: [{ type: 'text', text: opts.rawReply }], isError: false } }
    if (opts.isUp && !opts.isUp()) return { value: { content: [{ type: 'text', text: 'no connected MCP tool' }], isError: true } }
    if (opts.hubDown || e.server !== SERVER) return { value: { content: [{ type: 'text', text: 'no such server' }], isError: true } }
    const a = e.args
    const reply = (data: unknown) => ({ value: { content: [{ type: 'text', text: JSON.stringify(data) }], isError: false } })
    if (e.tool === 'mempalace_add_drawer') return reply({ success: true, drawer_id: 'drawer_fleet_presence_new' })
    if (e.tool === 'mempalace_update_drawer') return reply({ success: true, drawer_id: e.args.drawer_id })
    if (e.tool === 'mempalace_list_drawers') return reply({ drawers: (opts.presence ?? []).map(p => ({ content_preview: p })) })
    if (e.tool === 'mempalace_mesh_peers') return { value: { content: [{ type: 'text', text: JSON.stringify({ peers: opts.meshPeers ?? [] }) }], isError: false } }
    let events: unknown[] = []
    if (a.writer === ME || a.from_agent === ME) events = [MY_ACK]
    else if (a.type === 'task.request') events = [TASK_NEEDS_XCODE, TASK_ACKED]
    else if (a.since_event_id === 'evt_00') events = [TASK_NEEDS_XCODE]
    else if (a.since_event_id === 'evt_w1') events = opts.newMail ?? []
    else if (a.limit === 1) events = []
    else if (a.limit === 40 && !a.before_event_id) events = [MY_ACK, TASK_ACKED, TASK_NEEDS_XCODE]
    else if (a.before_event_id) events = []
    return { value: { content: [{ type: 'text', text: JSON.stringify({ events, count: events.length }) }], isError: false } }
  })
  const deliver = (result: { additionalContext?: readonly string[] }) => conversation.push(...(result.additionalContext ?? []))
  return { calls, mcp, beneath, deliver }
}

describe('helpers', () => {
  test('requirements from metadata and from a Requires line', () => {
    expect(requiresOf({ metadata: { requires: 'a, b>=2' } })).toEqual(['a', 'b>=2'])
    expect(requiresOf({ body: 'x\nRequires: c d' })).toEqual(['c', 'd'])
    expect(requiresOf({})).toEqual([])
  })

  test('version comparisons', () => {
    const caps = { xcode: { present: true, version: '27.1' } }
    expect(unmetRequirements(['xcode>=27', 'xcode=27'], caps)).toEqual([])
    expect(unmetRequirements(['xcode>27.1', 'xcode<27', 'gpu', 'bad req!!'], caps)).toEqual(
      ['xcode>27.1 (have 27.1)', 'xcode<27 (have 27.1)', 'gpu', 'bad req!! (unreadable)'])
  })

  test('excerpts are cleaned and flagged', () => {
    const item = toItem({ id: 'e', type: 'task.request', body: 'line one\n\u0007line two', metadata: { requires: ['gpu'] } }, {})
    expect(item.excerpt).toBe('line one line two')
    expect(itemLine(item)).toContain('THIS MACHINE CANNOT MEET: gpu')
  })
})

describe('session start and the first prompt', () => {
  test('session start only tags the event and announces the sweep', async ($, on) => {
    const { beneath, mcp } = world(on)
    const result = await $.classic.SessionStart({ source: 'startup' } as never)
    expect(beneath[0]?.mempalace_sharedbrain_mod).toBe('active')
    expect(result.additionalContext?.[0]).toBe('COMMAND-HOOK BLOCK')
    expect((result.additionalContext ?? []).join('\n')).toContain('checks it through the session\'s MCP connection when the first prompt arrives')
    expect(mcp.length).toBe(0)
  })

  test('the first prompt sweeps; the cursor is recorded once the message reached the model', async ($, on) => {
    const { calls, deliver } = world(on)
    await $.classic.SessionStart({ source: 'startup' } as never)
    const result = await $.classic.UserPromptSubmit({ prompt: 'hello' } as never)
    const text = (result.additionalContext ?? []).join('\n')
    expect(text).toContain(`checked by the mempalace-sharedbrain mod through the MCP server "${SERVER}"`)
    expect(text).toContain('evt_01')
    expect(text).toContain('THIS MACHINE CANNOT MEET: xcode>=27')
    expect(text).toContain('with no ack from this identity: 1')
    expect(text).not.toContain('done already')
    expect(text).toContain('once this message has reached you')
    expect(calls).not.toContainEqual(['cursor', 'set', 'evt_01'])
    deliver(result)
    await $.classic.Stop({ stop_hook_active: false } as never)
    expect(calls).toContainEqual(['cursor', 'set', 'evt_01'])
    const second = await $.classic.UserPromptSubmit({ prompt: 'again' } as never)
    expect(second.additionalContext ?? []).toEqual([])
  })

  test('a message that never reached the model is shown again and the cursor stays', async ($, on) => {
    const { calls } = world(on)
    await $.classic.SessionStart({ source: 'startup' } as never)
    await $.classic.UserPromptSubmit({ prompt: 'hello' } as never) // its result is dropped: nothing delivered
    await $.classic.Stop({ stop_hook_active: false } as never)
    expect(calls).not.toContainEqual(['cursor', 'set', 'evt_01'])
    const again = await $.classic.UserPromptSubmit({ prompt: 'next' } as never)
    expect((again.additionalContext ?? []).join('\n')).toContain('evt_01')
    expect(calls).not.toContainEqual(['cursor', 'set', 'evt_01'])
  })

  test('a configured server that does not answer falls back to the model sweep', async ($, on) => {
    const { mcp } = world(on, { ctx: context({ mcp_server: 'elsewhere' }) })
    await $.classic.SessionStart({ source: 'startup' } as never)
    const first = await $.classic.UserPromptSubmit({ prompt: 'one' } as never)
    expect((first.additionalContext ?? []).join('\n')).toContain('tries again with the next prompt')
    await $.classic.UserPromptSubmit({ prompt: 'two' } as never)
    const result = await $.classic.UserPromptSubmit({ prompt: 'three' } as never)
    const text = (result.additionalContext ?? []).join('\n')
    expect(text).toContain('the inbox check through MCP failed 3 times')
    expect(text).toContain(`since_event_id=evt_00`)
    expect(mcp.every(c => c.tool === 'mempalace_event_list')).toBe(true)
  })

  test('says so when the hub cannot be reached', async ($, on) => {
    world(on, { hubDown: true })
    await $.classic.SessionStart({ source: 'startup' } as never)
    for (const prompt of ['one', 'two']) {
      const early = await $.classic.UserPromptSubmit({ prompt } as never)
      expect((early.additionalContext ?? []).join('\n')).not.toContain('sweep it yourself now')
    }
    const result = await $.classic.UserPromptSubmit({ prompt: 'three' } as never)
    expect((result.additionalContext ?? []).join('\n')).toContain('sweep it yourself now')
    const after = await $.classic.UserPromptSubmit({ prompt: 'four' } as never)
    expect(after.additionalContext ?? []).toEqual([])
  })

  test('a connector that comes up on a later prompt is swept then', async ($, on) => {
    let up = false
    const { calls, deliver } = world(on, { isUp: () => up })
    await $.classic.SessionStart({ source: 'startup' } as never)
    const first = await $.classic.UserPromptSubmit({ prompt: 'one' } as never)
    expect((first.additionalContext ?? []).join('\n')).toContain('tries again with the next prompt')
    up = true
    const second = await $.classic.UserPromptSubmit({ prompt: 'two' } as never)
    expect((second.additionalContext ?? []).join('\n')).toContain('checked by the mempalace-sharedbrain mod')
    deliver(second)
    await $.classic.Stop({ stop_hook_active: false } as never)
    expect(calls).toContainEqual(['cursor', 'set', 'evt_01'])
  })
})

describe('wake check', () => {
  test('undelivered mail is handed over again, once', async ($, on) => {
    const mail = [{ id: 'evt_w2', type: 'task.reply', from_agent: 'peer', to_agent: ME, body: 'patch is ready' }]
    const { calls, deliver } = world(on, { ctx: context({ watch: { armed: true, since_event_id: 'evt_w1' } }), newMail: mail })
    await $.classic.UserPromptSubmit({ prompt: 'one' } as never) // dropped
    const again = await $.classic.UserPromptSubmit({ prompt: 'two' } as never)
    const text = (again.additionalContext ?? []).join('\n')
    expect(text).toContain('MEMPALACE WAKE: 1 coordination event')
    expect(text.split('patch is ready').length - 1).toBe(1)
    deliver(again)
    await $.classic.Stop({ stop_hook_active: false } as never)
    expect(calls).toContainEqual(['listen', 'cursor', 'evt_w2'])
  })

  test('hands new mail over with the prompt while listening', async ($, on) => {
    const mail = [{ id: 'evt_w2', type: 'task.reply', from_agent: 'peer', to_agent: ME, body: 'patch is ready' },
                  { id: 'evt_w3', type: 'task.reply', from_agent: ME, to_agent: ME, body: 'my own' }]
    const { calls, deliver } = world(on, { ctx: context({ watch: { armed: true, since_event_id: 'evt_w1' } }), newMail: mail })
    const result = await $.classic.UserPromptSubmit({ prompt: 'hello' } as never)
    const text = (result.additionalContext ?? []).join('\n')
    expect(text).toContain('MEMPALACE WAKE: 1 coordination event')
    expect(text).toContain('patch is ready')
    expect(text).not.toContain('my own')
    expect(calls).not.toContainEqual(['listen', 'cursor', 'evt_w3'])
    deliver(result)
    await $.classic.Stop({ stop_hook_active: false } as never)
    expect(calls).toContainEqual(['listen', 'cursor', 'evt_w3'])
  })

  test('adds nothing after the first prompt when not listening', async ($, on) => {
    const { beneath, deliver } = world(on)
    deliver(await $.classic.UserPromptSubmit({ prompt: 'first' } as never))
    const result = await $.classic.UserPromptSubmit({ prompt: 'hello' } as never)
    expect(beneath.at(-1)?.mempalace_sharedbrain_mod).toBe('active')
    expect(result.additionalContext ?? []).toEqual([])
  })
})

describe('pane after a check', () => {
  for (const surface of ['terminal', 'desktop'] as const) {
    test(`shows the identity and the open tasks (${surface})`, async ($, on) => {
      world(on)
      await $.classic.UserPromptSubmit({ prompt: 'hello' } as never)
      const ui = await $.ui.mount({ plugin: 'mempalace-sharedbrain', surface, component: 'Pane', requestId: 'mempalace-hub',
        props: { title: 'MemPalace shared brain', isFocused: false, bodyColumns: 80, placement: 'dock' } } as never)
      expect(await ui.find({ text: ME })).toBeDefined()
      expect(await ui.find({ text: /Open tasks \(1\)/ })).toBeDefined()
      expect(await ui.find({ text: /Build the iOS app/ })).toBeDefined()
      expect(await ui.find({ text: /cannot meet: xcode>=27/ })).toBeDefined()
    })
  }
})

describe('sessions', () => {
  test('the table lists identities newest first and marks this session and flat names', () => {
    const now = Date.parse('2026-10-04T10:20:00Z')
    const text = sessionsTable([
      { from_agent: ME, created_at: '2026-10-04T10:16:00Z' },
      { from_agent: 'mac-mini:claude:projects', created_at: '2026-10-04T10:14:00Z' },
      { from_agent: 'mac-mini:claude:projects', created_at: '2026-10-04T09:00:00Z' },
      { from_agent: 'unraid-hermes', created_at: '2026-10-01T04:00:00Z' },
    ], ME, SERVER, now)
    const rows = text.split('\n').filter(l => l.startsWith('  '))
    expect(rows[0]).toContain(ME)
    expect(rows[0]).toContain('this session')
    expect(rows[1]).toContain('mac-mini:claude:projects')
    expect(rows[1]).toContain('2 events')
    expect(rows[2]).toContain('unraid-hermes')
    expect(rows[2]).toContain('fixed or legacy name')
    expect(rows[2]).toContain('3 days ago')
  })

  test('an unreadable reply is an error, not an empty hub', async ($, on) => {
    world(on, { rawReply: '{"events": [{"id": "evt_cut' })
    const out = await $.command.run({ command: 'mempalace-sharedbrain:sessions', args: '' } as never)
    expect(JSON.stringify(out)).toContain('could not be read')
  })

  test('the command answers from the hub without the model', async ($, on) => {
    world(on)
    const out = await $.command.run({ command: 'mempalace-sharedbrain:sessions', args: '' } as never)
    expect(JSON.stringify(out)).toContain('Agents writing to the hub')
  })
})

describe('peers in the menu', () => {
  const describePeers = ($: { command: { describe: (e: never) => Promise<{ isHidden: boolean }> } }) =>
    $.command.describe({ command: 'mempalace-sharedbrain:peers', description: 'Show the shared-brain fleet state', isHidden: false } as never)

  test('hidden on a single hub reached through the connector', async ($, on) => {
    const { deliver } = world(on)
    deliver(await $.classic.UserPromptSubmit({ prompt: 'hello' } as never))
    expect((await describePeers($ as never)).isHidden).toBe(true)
  })

  test('shown when the hub has mesh peers', async ($, on) => {
    world(on, { meshPeers: [{ name: 'peer-hub' }] })
    await $.classic.UserPromptSubmit({ prompt: 'hello' } as never)
    expect((await describePeers($ as never)).isHidden).toBe(false)
  })
})

describe('presence', () => {
  test('the first check adds this identity\'s check-in drawer and remembers it', async ($, on) => {
    const { calls, mcp, deliver } = world(on)
    deliver(await $.classic.UserPromptSubmit({ prompt: 'hello' } as never))
    const added = mcp.find(c => c.tool === 'mempalace_add_drawer')
    expect(added?.args.room).toBe('presence')
    expect(String(added?.args.content)).toContain(`identity: ${ME} | checked_in `)
    expect(added?.args.added_by).toBe(ME)
    expect(calls).toContainEqual(['presence', 'set', 'drawer_fleet_presence_new'])
  })

  test('a known drawer is updated in place', async ($, on) => {
    const { mcp } = world(on, { ctx: context({ presence: { enabled: true, wing: 'fleet', room: 'presence', interval_minutes: 30, drawer_id: 'drawer_fleet_presence_mine' } }) })
    await $.classic.UserPromptSubmit({ prompt: 'hello' } as never)
    expect(mcp.some(c => c.tool === 'mempalace_update_drawer' && c.args.drawer_id === 'drawer_fleet_presence_mine')).toBe(true)
    expect(mcp.some(c => c.tool === 'mempalace_add_drawer')).toBe(false)
  })

  test('sessions lists check-ins newest first and marks idle ones', async ($, on) => {
    const fresh = new Date(Date.now() - 5 * 60_000).toISOString()
    const old = new Date(Date.now() - 5 * 3600_000).toISOString()
    world(on, { presence: [
      `identity: mac-mini:claude:projects | checked_in ${old} | plugin 0.4.9 mod | listening no | host mac-mini | project projects`,
      `identity: ${ME} | checked_in ${fresh} | plugin 0.4.9 mod | listening yes | host office-desktop | project demo`,
      'some other drawer in the room',
    ] })
    const out = JSON.stringify(await $.command.run({ command: 'mempalace-sharedbrain:sessions', args: '' } as never))
    expect(out).toContain('Sessions checked in to the hub')
    expect(out.indexOf(ME)).toBeLessThan(out.indexOf('mac-mini:claude:projects'))
    expect(out).toContain('active, this session, listening')
    expect(out).toContain('(idle)')
  })

  test('parseCheckIn reads only check-in lines', () => {
    expect(parseCheckIn('identity: a:b:c | checked_in 2026-10-04T10:00:00Z | plugin 0.4.9 mod | listening no | host a | project c')?.project).toBe('c')
    expect(parseCheckIn('anything else')).toBeNull()
  })
})
