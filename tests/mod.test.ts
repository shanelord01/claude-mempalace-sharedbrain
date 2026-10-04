// Run with: claude plugin test .
// The test's `on` hooks sit beneath the mod and stand for the engine: they answer $.process.run (the
// plugin's Python) and $.mcp.call (the hub) from memory.
import { describe, expect, mock, test } from 'claude-code/testing'

import { itemLine, requiresOf, toItem, unmetRequirements } from '../hooks/register'

const ME = 'office-desktop:claude:demo'
const SERVER = 'claude.ai Mempalace'

type Ctx = Record<string, unknown>

function context(over: Ctx = {}): Ctx {
  return {
    identity: ME, diary: 'office-desktop_claude_demo', cursor: 'evt_00', watch: {}, mcp_server: '',
    inbox_limit: 10, sweep: true, wake_types: ['task.request', 'task.reply', 'patch.ready'], wake_limit: 50,
    version: '0.4.0', capabilities: { python: { present: true, version: '3.14.7' }, 'memory-gb': { present: true, version: '62' } },
    ...over,
  }
}

const TASK_NEEDS_XCODE = {
  id: 'evt_01', type: 'task.request', status: 'open', from_agent: 'mac-mini:claude:app', to_agent: ME,
  created_at: '2026-10-04T00:00:00Z', body: 'Build the iOS app', metadata: { requires: ['xcode>=27'] },
}
const TASK_ACKED = { id: 'evt_02', type: 'task.request', status: 'open', from_agent: 'other', to_agent: '*', body: 'done already' }
const MY_ACK = { id: 'evt_03', type: 'event.ack', from_agent: ME, metadata: { ack_of: 'evt_02' } }

function world(on: Parameters<Parameters<typeof test>[1] & Function>[1], opts: { ctx?: Ctx; hubDown?: boolean; newMail?: unknown[] } = {}) {
  const calls: string[][] = []
  const mcp: Array<{ tool: string; args: Record<string, unknown> }> = []
  const beneath: Array<Record<string, unknown>> = []
  mock.env(on, {})
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
  on('process.run', async (_$: unknown, e: { argv: readonly string[] }) => {
    const args = e.argv.slice(2)
    calls.push([...args])
    if (e.argv.includes('--cwd')) expect(e.argv[e.argv.indexOf('--cwd') + 1]).toBe('/tmp/demo')
    if (args[0] === 'mod-context') return { value: { exitCode: 0, stdout: JSON.stringify(opts.ctx ?? context()), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    return { value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('mcp.call', async (_$: unknown, e: { server: string; tool: string; args: Record<string, unknown> }) => {
    mcp.push({ tool: e.tool, args: e.args })
    if (opts.hubDown || e.server !== SERVER) return { value: { content: [{ type: 'text', text: 'no such server' }], isError: true } }
    const a = e.args
    let events: unknown[] = []
    if (a.writer === ME || a.from_agent === ME) events = [MY_ACK]
    else if (a.type === 'task.request') events = [TASK_NEEDS_XCODE, TASK_ACKED]
    else if (a.since_event_id === 'evt_00') events = [TASK_NEEDS_XCODE]
    else if (a.since_event_id === 'evt_w1') events = opts.newMail ?? []
    else if (a.limit === 1) events = []
    return { value: { content: [{ type: 'text', text: JSON.stringify({ events, count: events.length }) }], isError: false } }
  })
  return { calls, mcp, beneath }
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

  test('the first prompt sweeps the inbox through MCP and records the cursor', async ($, on) => {
    const { calls } = world(on)
    await $.classic.SessionStart({ source: 'startup' } as never)
    const result = await $.classic.UserPromptSubmit({ prompt: 'hello' } as never)
    const text = (result.additionalContext ?? []).join('\n')
    expect(text).toContain(`checked by the mempalace-sharedbrain mod through the MCP server "${SERVER}"`)
    expect(text).toContain('evt_01')
    expect(text).toContain('THIS MACHINE CANNOT MEET: xcode>=27')
    expect(text).toContain('with no ack from this identity: 1')
    expect(text).not.toContain('done already')
    expect(calls).toContainEqual(['cursor', 'set', 'evt_01'])
    const second = await $.classic.UserPromptSubmit({ prompt: 'again' } as never)
    expect(second.additionalContext ?? []).toEqual([])
  })

  test('a configured server that does not answer falls back to the model sweep', async ($, on) => {
    const { mcp } = world(on, { ctx: context({ mcp_server: 'elsewhere' }) })
    await $.classic.SessionStart({ source: 'startup' } as never)
    const result = await $.classic.UserPromptSubmit({ prompt: 'hello' } as never)
    const text = (result.additionalContext ?? []).join('\n')
    expect(text).toContain('the inbox check through MCP failed')
    expect(text).toContain(`since_event_id=evt_00`)
    expect(mcp.every(c => c.tool === 'mempalace_event_list')).toBe(true)
  })

  test('says so when the hub cannot be reached', async ($, on) => {
    world(on, { hubDown: true })
    await $.classic.SessionStart({ source: 'startup' } as never)
    const result = await $.classic.UserPromptSubmit({ prompt: 'hello' } as never)
    expect((result.additionalContext ?? []).join('\n')).toContain('sweep it yourself now')
  })
})

describe('wake check', () => {
  test('hands new mail over with the prompt while listening', async ($, on) => {
    const mail = [{ id: 'evt_w2', type: 'task.reply', from_agent: 'peer', to_agent: ME, body: 'patch is ready' },
                  { id: 'evt_w3', type: 'task.reply', from_agent: ME, to_agent: ME, body: 'my own' }]
    const { calls } = world(on, { ctx: context({ watch: { armed: true, since_event_id: 'evt_w1' } }), newMail: mail })
    const result = await $.classic.UserPromptSubmit({ prompt: 'hello' } as never)
    const text = (result.additionalContext ?? []).join('\n')
    expect(text).toContain('MEMPALACE WAKE: 1 coordination event')
    expect(text).toContain('patch is ready')
    expect(text).not.toContain('my own')
    expect(calls).toContainEqual(['listen', 'cursor', 'evt_w3'])
  })

  test('adds nothing after the first prompt when not listening', async ($, on) => {
    const { beneath } = world(on)
    await $.classic.UserPromptSubmit({ prompt: 'first' } as never)
    const result = await $.classic.UserPromptSubmit({ prompt: 'hello' } as never)
    expect(beneath.at(-1)?.mempalace_sharedbrain_mod).toBe('active')
    expect(result.additionalContext ?? []).toEqual([])
  })
})
