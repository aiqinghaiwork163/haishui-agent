import { useQuery } from '@tanstack/react-query'

import { getHaishuiConfigRecord, type ProfileScope, profileScopeKey } from '@/haishui'
import { queryClient, writeCache } from '@/lib/query-client'
import type { HaishuiConfigRecord } from '@/types/haishui'

// One shared cache for the whole profile config record (`GET /api/config`).
// Every settings surface (MCP, model, config) reads and writes through this key
// so a save in one shows in the others, and revisiting a tab paints the cache
// instead of blanking on a fresh fetch.
//
// Distinct from session/hooks/use-haishui-config.ts, which is side-effecting —
// it pushes personality/cwd/voice/… into the session stores for live chat.
export const HAISHUI_CONFIG_KEY = ['haishui-config-record'] as const

// Per-scope cache key. The base key (no suffix) is the app-wide active
// profile, unchanged for every caller that passes nothing. An explicit scope —
// the Capabilities scope selector configuring ANOTHER profile, possibly on
// another registered gateway — gets its own suffixed key so switching the
// selector refetches and never paints stale cross-profile config (the
// AGENTS.md scope-in-key rule). profileScopeKey folds a remote pin's
// connection id into the suffix, so two gateways' same-named profiles never
// share a cache row.
export const haishuiConfigKey = (profile?: ProfileScope) =>
  profile == null ? HAISHUI_CONFIG_KEY : ([...HAISHUI_CONFIG_KEY, profileScopeKey(profile)] as const)

// staleTime 0 → serve cache instantly, background-revalidate on every mount.
// `profile` scopes both the query key and the fetch; omitting it preserves the
// exact app-wide behavior (base key, `profileScoped(undefined)` fallback).
export const useHaishuiConfigRecord = (profile?: ProfileScope) =>
  useQuery({
    queryKey: haishuiConfigKey(profile),
    // null/undefined both mean "no override" → fetch with undefined so
    // capabilityScoped falls back to the app-wide active profile (passing null
    // would wrongly target the primary backend).
    queryFn: () => getHaishuiConfigRecord(profile ?? undefined),
    staleTime: 0
  })

// setHaishuiConfigCache writes the app-wide (base-key) record. Pass a profile to
// write the suffixed per-profile cache instead — keeps the selector's optimistic
// write-through landing on the same key its query reads.
export const setHaishuiConfigCache = writeCache<HaishuiConfigRecord>(HAISHUI_CONFIG_KEY)
export const haishuiConfigCacheWriter = (profile?: ProfileScope) =>
  writeCache<HaishuiConfigRecord>(haishuiConfigKey(profile))

export const invalidateHaishuiConfig = (profile?: ProfileScope) =>
  queryClient.invalidateQueries({ queryKey: haishuiConfigKey(profile) })
