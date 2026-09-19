import { describe, expect, it } from 'vitest'

import {
  normalizeHaishuiOpenString,
  pathFromHaishuiDeepLink,
  pathFromOpenDeepLink,
  resolveHaishuiOpenPath
} from './haishui-open-target'

describe('normalizeHaishuiOpenString', () => {
  it('accepts hash-router paths and strips a leading hash', () => {
    expect(normalizeHaishuiOpenString('/index-network/intent/1')).toBe('/index-network/intent/1')
    expect(normalizeHaishuiOpenString('#/index-network/intent/1')).toBe('/index-network/intent/1')
  })

  it('maps plugin-scoped haishui:// deep links to the same path', () => {
    expect(normalizeHaishuiOpenString('haishui://index-network/intent/1')).toBe('/index-network/intent/1')
    expect(normalizeHaishuiOpenString('haishui://index-network/intent/1?focus=true')).toBe(
      '/index-network/intent/1?focus=true'
    )
  })

  it('maps haishui://open/… deep links by stripping the open host', () => {
    expect(normalizeHaishuiOpenString('haishui://open/index-network/intent/1')).toBe('/index-network/intent/1')
    expect(normalizeHaishuiOpenString('haishui://open/settings/plugins')).toBe('/settings/plugins')
  })

  it('rejects reserved haishui kinds and unsafe paths', () => {
    expect(normalizeHaishuiOpenString('haishui://blueprint/morning-brief')).toBeNull()
    expect(normalizeHaishuiOpenString('haishui://plugin/install')).toBeNull()
    expect(normalizeHaishuiOpenString('https://example.com/x')).toBeNull()
    expect(normalizeHaishuiOpenString('/../etc/passwd')).toBeNull()
    expect(normalizeHaishuiOpenString('index-network')).toBeNull()
  })
})

describe('resolveHaishuiOpenPath', () => {
  it('merges structured path + params', () => {
    expect(resolveHaishuiOpenPath({ path: '/index-network/intent/1', params: { focus: 'true' } })).toBe(
      '/index-network/intent/1?focus=true'
    )
  })

  it('resolves href the same as a bare string', () => {
    expect(resolveHaishuiOpenPath({ href: 'haishui://index-network/intent/1' })).toBe('/index-network/intent/1')
  })
})

describe('pathFromHaishuiDeepLink', () => {
  it('builds the navigate path from a plugin-scoped deep-link payload', () => {
    expect(pathFromHaishuiDeepLink('index-network', 'intent/1')).toBe('/index-network/intent/1')
  })

  it('builds the navigate path from haishui://open/… payloads', () => {
    expect(pathFromOpenDeepLink('index-network/intent/1')).toBe('/index-network/intent/1')
    expect(pathFromHaishuiDeepLink('open', 'agent/42')).toBe('/agent/42')
  })

  it('ignores reserved kinds', () => {
    expect(pathFromHaishuiDeepLink('blueprint', 'morning-brief')).toBeNull()
    expect(pathFromHaishuiDeepLink('plugin', 'install')).toBeNull()
  })
})
