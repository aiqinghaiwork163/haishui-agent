import { contextBridge, ipcRenderer, webFrame, webUtils } from 'electron'

import type { DesktopProfileRoute } from './desktop-profile'
import { customWindowControlsEnabled } from './window-controls'

// Which translucency the OS can back. Asked synchronously because the renderer
// needs it before its first paint, and answered by main because deciding it
// needs `os.release()` — a sandboxed preload may only require electron, events,
// timers and url, so importing node:os here throws before contextBridge runs
// and takes the ENTIRE bridge down with it (window.haishuiDesktop undefined =>
// "Desktop IPC bridge is unavailable"). No reply means no glass, which degrades
// to an ordinary opaque window rather than a page thinned over nothing.
const translucencySupport = ipcRenderer.sendSync('haishui:translucency:support')
const hudWindowing = ipcRenderer.sendSync('haishui:hud:windowing')
const hudNativeDrag = hudWindowing?.nativeDrag === true
const launchFlags = ipcRenderer.sendSync('haishui:launch-flags')

contextBridge.exposeInMainWorld('haishuiDesktop', {
  glassSupported: translucencySupport?.glass === true,
  translucencySupported: translucencySupport?.translucency === true,
  // Launch-flag fact: the app was started with --local, so the renderer may
  // show the local-models surfaces. Static for the window's lifetime.
  localModelsEnabled: launchFlags?.localModels === true,
  // Launch-flag fact: the Nous free tier is on for this launch
  // (HAISHUI_GUEST_ONBOARDING=1 or --guest-onboarding). Read-only; the same
  // decision is stamped onto every backend the app spawns.
  guestOnboardingEnabled: launchFlags?.guestOnboarding === true,
  // Launch-flag fact: skip the first-run film (HAISHUI_SKIP_INTRO=1 or
  // --skip-intro). Rehearsal aid for the guided chat behind it.
  skipIntro: launchFlags?.skipIntro === true,
  getConnection: (profile, opts) => ipcRenderer.invoke('haishui:connection', profile, opts),
  // Registry-scoped backend resolution: { connectionId, profile } → descriptor.
  getConnectionFor: payload => ipcRenderer.invoke('haishui:connection:for', payload),
  getProfileRoutes: profiles => ipcRenderer.invoke('haishui:plugin-profile-routes', profiles),
  revalidateConnection: () => ipcRenderer.invoke('haishui:connection:revalidate'),
  touchBackend: (profile, options) => ipcRenderer.invoke('haishui:backend:touch', profile, options),
  getPoolLimits: () => ipcRenderer.invoke('haishui:pool-limits:get'),
  setPoolLimits: limits => ipcRenderer.invoke('haishui:pool-limits:set', limits),
  getGatewayWsUrl: profile => ipcRenderer.invoke('haishui:gateway:ws-url', profile),
  // Registry-scoped fresh WS URL: { connectionId, profile } → result shape of
  // getGatewayWsUrl, minted against that connection's backend.
  getGatewayWsUrlFor: payload => ipcRenderer.invoke('haishui:gateway:ws-url-for', payload),
  // Union agent roster across every registered connection.
  getAgentRoster: () => ipcRenderer.invoke('haishui:agents:roster'),
  openSessionWindow: (sessionId, opts) => ipcRenderer.invoke('haishui:window:openSession', sessionId, opts),
  openSessionInTerminal: (sessionId, opts) => ipcRenderer.invoke('haishui:window:openInTerminal', sessionId, opts),
  openWindow: (options?: DesktopProfileRoute) => ipcRenderer.invoke('haishui:window:openInstance', options),
  openBrowserWindow: tabId => ipcRenderer.invoke('haishui:window:openBrowser', tabId),
  onBrowserPopoutClosed: callback => {
    const listener = (_event, tabId) => callback(tabId)
    ipcRenderer.on('haishui:browser-popout:closed', listener)

    return () => ipcRenderer.removeListener('haishui:browser-popout:closed', listener)
  },
  claimAmbientCue: key => ipcRenderer.invoke('haishui:ambient:claim', key),
  windowControls: {
    custom: customWindowControlsEnabled(),
    minimize: () => ipcRenderer.send('haishui:window-control', 'minimize'),
    toggleMaximize: () => ipcRenderer.send('haishui:window-control', 'toggle-maximize'),
    close: () => ipcRenderer.send('haishui:window-control', 'close')
  },
  wakeIndicator: {
    getState: () => ipcRenderer.invoke('haishui:wake-indicator:get'),
    setState: state => ipcRenderer.send('haishui:wake-indicator:set', state),
    onState: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('haishui:wake-indicator:state', listener)

      return () => ipcRenderer.removeListener('haishui:wake-indicator:state', listener)
    }
  },
  chatOnboarding: {
    grow: request => ipcRenderer.send('haishui:chat-onboarding:grow', request),
    soloBoot: () => ipcRenderer.send('haishui:chat-onboarding:solo-boot')
  },
  introReveal: {
    open: (payload?: { hideMain?: boolean }) => ipcRenderer.invoke('haishui:intro-reveal:open', payload),
    close: (payload?: { showMain?: boolean }) => ipcRenderer.invoke('haishui:intro-reveal:close', payload),
    skip: () => ipcRenderer.send('haishui:intro-reveal:skip'),
    ready: () => ipcRenderer.send('haishui:intro-reveal:ready'),
    onSkip: callback => {
      const listener = () => callback()

      ipcRenderer.on('haishui:intro-reveal:skip', listener)

      return () => ipcRenderer.removeListener('haishui:intro-reveal:skip', listener)
    },
    onClosed: callback => {
      const listener = () => callback()

      ipcRenderer.on('haishui:intro-reveal:closed', listener)

      return () => ipcRenderer.removeListener('haishui:intro-reveal:closed', listener)
    }
  },
  petOverlay: {
    // Main renderer → main process: window lifecycle + drag. `request` is
    // `{ bounds, screen }`; resolves with the screen bounds it actually used.
    open: request => ipcRenderer.invoke('haishui:pet-overlay:open', request),
    close: () => ipcRenderer.invoke('haishui:pet-overlay:close'),
    setBounds: bounds => ipcRenderer.send('haishui:pet-overlay:set-bounds', bounds),
    setIgnoreMouse: ignore => ipcRenderer.send('haishui:pet-overlay:ignore-mouse', ignore),
    // Flip the overlay focusable (and focus it) while the composer needs keys.
    setFocusable: focusable => ipcRenderer.send('haishui:pet-overlay:set-focusable', focusable),
    // Main renderer → overlay (forwarded by main): push the latest pet state.
    pushState: payload => ipcRenderer.send('haishui:pet-overlay:state', payload),
    // Overlay → main renderer (forwarded by main): pop back in / composer submit.
    control: payload => ipcRenderer.send('haishui:pet-overlay:control', payload),
    // Overlay subscribes to state pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('haishui:pet-overlay:state', listener)

      return () => ipcRenderer.removeListener('haishui:pet-overlay:state', listener)
    },
    // Main renderer subscribes to overlay control messages.
    onControl: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('haishui:pet-overlay:control', listener)

      return () => ipcRenderer.removeListener('haishui:pet-overlay:control', listener)
    }
  },
  // HUD mode: the chrome-free floating chat. A full app renderer (own gateway)
  // sized as a floating bar, so it mounts the real composer. Main owns the
  // window; `onChanged` keeps every window's toggle truthful.
  hud: {
    nativeDrag: hudNativeDrag,
    windowing: {
      clientPlacement: hudWindowing?.clientPlacement !== false,
      controlDrag: hudWindowing?.controlDrag === true,
      nativeDrag: hudNativeDrag,
      solid: hudWindowing?.solid === true,
      workspaceTransfer: hudWindowing?.workspaceTransfer === true
    },
    open: request => ipcRenderer.invoke('haishui:hud:open', request),
    close: () => ipcRenderer.invoke('haishui:hud:close'),
    setIgnoreMouse: ignore => ipcRenderer.send('haishui:hud:ignore-mouse', ignore),
    beginMove: () => ipcRenderer.send('haishui:hud:begin-move'),
    endMove: () => ipcRenderer.send('haishui:hud:end-move'),
    moveBy: delta => ipcRenderer.send('haishui:hud:move-by', delta),
    setWorkspaceTransfer: transferring => ipcRenderer.send('haishui:hud:workspace-transfer', transferring),
    setBounds: bounds => ipcRenderer.send('haishui:hud:set-bounds', bounds),
    resetLayout: () => ipcRenderer.invoke('haishui:hud:reset-layout'),
    // Whether the band covers the window below the bar. Main pairs it with the
    // user's translucency setting to decide the native frost (macOS vibrancy /
    // Windows 11 DWM backdrop) — see hudFrostFor.
    setFrost: showing => ipcRenderer.invoke('haishui:hud:frost', showing),
    // The HUD tells main which session it is on; main hands that back to the
    // app window when the HUD closes, so the app can re-home onto it.
    setSession: sessionId => ipcRenderer.send('haishui:hud:session', sessionId),
    onGoto: callback => {
      const listener = (_event, sessionId) => callback(sessionId)
      ipcRenderer.on('haishui:hud:goto', listener)

      return () => ipcRenderer.removeListener('haishui:hud:goto', listener)
    },
    onChanged: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('haishui:hud:changed', listener)

      return () => ipcRenderer.removeListener('haishui:hud:changed', listener)
    },
    // Linux only, and silent elsewhere: where the cursor is, in page
    // coordinates, or null when it has left the window. Stands in for the
    // mousemove that `setIgnoreMouseEvents(true, { forward: true })` delivers on
    // macOS and Windows but not here.
    onCursor: callback => {
      const listener = (_event, point) => callback(point)
      ipcRenderer.on('haishui:hud:cursor', listener)

      return () => ipcRenderer.removeListener('haishui:hud:cursor', listener)
    },
    // Main's game-overlay watch: whether a fullscreen app (a game) is under
    // the HUD, so the renderer can step back to the low-opacity overlay
    // treatment while one owns the screen.
    onGameOverlay: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('haishui:hud:game-overlay', listener)

      return () => ipcRenderer.removeListener('haishui:hud:game-overlay', listener)
    }
  },
  // macOS native screenshot gesture; captures require a main-issued request.
  screenshot: process.platform === 'darwin' ? {
    getSettings: () => ipcRenderer.invoke('haishui:screenshot:settings:get'),
    setEnabled: enabled => ipcRenderer.invoke('haishui:screenshot:settings:set', enabled),
    openPermissionSettings: kind => ipcRenderer.invoke('haishui:screenshot:permission', kind),
    capture: requestId => ipcRenderer.invoke('haishui:screenshot:capture', requestId),
    onStatus: callback => {
      const listener = (_event, status) => callback(status)
      ipcRenderer.on('haishui:screenshot:status', listener)

      return () => ipcRenderer.removeListener('haishui:screenshot:status', listener)
    },
    onRequest: callback => {
      const channel = 'haishui:screenshot:request'
      const listener = (_event, requestId) => callback(requestId)
      if (ipcRenderer.listenerCount(channel) === 0) {
        ipcRenderer.send('haishui:screenshot:subscribe', true)
      }
      ipcRenderer.on(channel, listener)

      return () => {
        ipcRenderer.removeListener(channel, listener)
        if (ipcRenderer.listenerCount(channel) === 0) {
          ipcRenderer.send('haishui:screenshot:subscribe', false)
        }
      }
    }
  } : undefined,
  // Quick Entry: the global-hotkey mini composer window. Main owns the OS
  // shortcut + the persisted preference; the quick window only captures text
  // and hands it back, and the primary renderer submits it through the normal
  // prompt path.
  quickEntry: {
    getSettings: () => ipcRenderer.invoke('haishui:quick-entry:settings:get'),
    setSettings: patch => ipcRenderer.invoke('haishui:quick-entry:settings:set', patch),
    submit: payload => ipcRenderer.send('haishui:quick-entry:submit', payload),
    dismiss: () => ipcRenderer.send('haishui:quick-entry:dismiss'),
    // Primary renderer → main → quick window: gateway connection state + the
    // recent-session options the target picker offers. Main caches the latest
    // payload so a freshly spawned quick window starts from truth.
    pushState: payload => ipcRenderer.send('haishui:quick-entry:state', payload),
    // Quick window subscribes to those pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('haishui:quick-entry:state', listener)

      return () => ipcRenderer.removeListener('haishui:quick-entry:state', listener)
    },
    // Main → primary renderer: a submit captured by the quick window.
    onSubmit: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('haishui:quick-entry:submit', listener)

      return () => ipcRenderer.removeListener('haishui:quick-entry:submit', listener)
    },
    // Main → quick window: you were just summoned (reset draft + refocus).
    onShown: callback => {
      const listener = () => callback()
      ipcRenderer.on('haishui:quick-entry:shown', listener)

      return () => ipcRenderer.removeListener('haishui:quick-entry:shown', listener)
    }
  },
  getBootProgress: () => ipcRenderer.invoke('haishui:boot-progress:get'),
  getConnectionConfig: profile => ipcRenderer.invoke('haishui:connection-config:get', profile),
  saveConnectionConfig: payload => ipcRenderer.invoke('haishui:connection-config:save', payload),
  applyConnectionConfig: payload => ipcRenderer.invoke('haishui:connection-config:apply', payload),
  testConnectionConfig: payload => ipcRenderer.invoke('haishui:connection-config:test', payload),
  // Opt-in OS-keychain encryption for stored gateway secrets (default off —
  // see secret-storage-policy.ts). get never touches the OS keychain.
  getSecretStorageEncryption: () => ipcRenderer.invoke('haishui:secret-storage:get'),
  setSecretStorageEncryption: (on: boolean) => ipcRenderer.invoke('haishui:secret-storage:set', on),
  // v2 multi-connection registry: named agent sources (local / remote / cloud / ssh).
  connections: {
    list: () => ipcRenderer.invoke('haishui:connections:list'),
    save: payload => ipcRenderer.invoke('haishui:connections:save', payload),
    remove: id => ipcRenderer.invoke('haishui:connections:remove', id),
    setPrimary: id => ipcRenderer.invoke('haishui:connections:set-primary', id),
    setLaunchMode: mode => ipcRenderer.invoke('haishui:connections:set-launch-mode', mode),
    setLastUsed: id => ipcRenderer.invoke('haishui:connections:set-last-used', id),
    test: id => ipcRenderer.invoke('haishui:connections:test', id),
    updateManaged: id => ipcRenderer.invoke('haishui:connections:update-managed', id),
    // Fan out `haishui update` to every eligible registered connection.
    // Optional excludeIds skips rows the caller updates through another path.
    updateAll: options => ipcRenderer.invoke('haishui:connections:update-all', options),
    // Registry lifecycle push (main → renderer): a connection was removed or
    // materially edited, so secondaries scoped to it must be disposed (and,
    // for edits, re-dialed at the new target).
    onChanged: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('haishui:connections:changed', listener)

      return () => ipcRenderer.removeListener('haishui:connections:changed', listener)
    }
  },
  sshConfigHosts: () => ipcRenderer.invoke('haishui:ssh-config:hosts'),
  sshResolveHost: host => ipcRenderer.invoke('haishui:ssh-config:resolve', host),
  probeConnectionConfig: remoteUrl => ipcRenderer.invoke('haishui:connection-config:probe', remoteUrl),
  oauthLoginConnectionConfig: remoteUrl => ipcRenderer.invoke('haishui:connection-config:oauth-login', remoteUrl),
  oauthLogoutConnectionConfig: remoteUrl => ipcRenderer.invoke('haishui:connection-config:oauth-logout', remoteUrl),
  // Haishui Cloud: one portal login powers discovery + silent per-agent sign-in
  // (cloud-auto-discovery Phase 3).
  cloud: {
    status: () => ipcRenderer.invoke('haishui:cloud:status'),
    login: () => ipcRenderer.invoke('haishui:cloud:login'),
    logout: () => ipcRenderer.invoke('haishui:cloud:logout'),
    discover: org => ipcRenderer.invoke('haishui:cloud:discover', org),
    agentSignIn: dashboardUrl => ipcRenderer.invoke('haishui:cloud:agent-sign-in', dashboardUrl)
  },
  profile: {
    getDefault: () => ipcRenderer.invoke('haishui:profile:default:get'),
    setDefault: (route: DesktopProfileRoute) => ipcRenderer.invoke('haishui:profile:default:set', route),
    onDefaultChanged: (callback: (route: DesktopProfileRoute | null) => void) => {
      const listener = (_event: Electron.IpcRendererEvent, route: DesktopProfileRoute | null) => callback(route)
      ipcRenderer.on('haishui:profile:default:changed', listener)

      return () => ipcRenderer.removeListener('haishui:profile:default:changed', listener)
    },
    get: () => ipcRenderer.invoke('haishui:profile:get'),
    remember: name => ipcRenderer.invoke('haishui:profile:remember', name),
    set: name => ipcRenderer.invoke('haishui:profile:set', name)
  },
  api: request => ipcRenderer.invoke('haishui:api', request),
  notify: payload => ipcRenderer.invoke('haishui:notify', payload),
  requestMicrophoneAccess: () => ipcRenderer.invoke('haishui:requestMicrophoneAccess'),
  readWindowBelow: () => ipcRenderer.invoke('haishui:window:readBelow'),
  readFileDataUrl: filePath => ipcRenderer.invoke('haishui:readFileDataUrl', filePath),
  readFileDataUrlForAttach: filePath => ipcRenderer.invoke('haishui:readFileDataUrlForAttach', filePath),
  dataUrlReadMax: {
    get: () => ipcRenderer.invoke('haishui:data-url-read-max:get'),
    set: maxMb => ipcRenderer.invoke('haishui:data-url-read-max:set', maxMb)
  },
  readFileText: filePath => ipcRenderer.invoke('haishui:readFileText', filePath),
  readPluginSource: (filePath: string) => ipcRenderer.invoke('haishui:readPluginSource', filePath),
  selectPaths: options => ipcRenderer.invoke('haishui:selectPaths', options),
  selectSavePath: options => ipcRenderer.invoke('haishui:selectSavePath', options),
  writeClipboard: text => ipcRenderer.invoke('haishui:writeClipboard', text),
  readClipboard: () => ipcRenderer.invoke('haishui:readClipboard'),
  saveGatewayFile: payload => ipcRenderer.invoke('haishui:saveGatewayFile', payload),
  saveImageFromUrl: url => ipcRenderer.invoke('haishui:saveImageFromUrl', url),
  contextMenuEdit: command => ipcRenderer.invoke('haishui:context-menu:edit', command),
  contextMenuCopyImage: () => ipcRenderer.invoke('haishui:context-menu:copy-image'),
  contextMenuSpellcheck: action => ipcRenderer.invoke('haishui:context-menu:spellcheck', action),
  contextMenuGuestAddWord: payload => ipcRenderer.invoke('haishui:context-menu:guest-add-word', payload),
  onContextMenuSpellcheck: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('haishui:context-menu-spellcheck', listener)

    return () => ipcRenderer.removeListener('haishui:context-menu-spellcheck', listener)
  },
  saveImageBuffer: (data, ext, name) => ipcRenderer.invoke('haishui:saveImageBuffer', { data, ext, name }),
  capturePreview: payload => ipcRenderer.invoke('haishui:capturePreview', payload),
  savePastedText: text => ipcRenderer.invoke('haishui:savePastedText', { text }),
  saveClipboardImage: () => ipcRenderer.invoke('haishui:saveClipboardImage'),
  getPathForFile: file => {
    try {
      return webUtils.getPathForFile(file) || ''
    } catch {
      return ''
    }
  },
  normalizePreviewTarget: (target, baseDir) => ipcRenderer.invoke('haishui:normalizePreviewTarget', target, baseDir),
  watchPreviewFile: url => ipcRenderer.invoke('haishui:watchPreviewFile', url),
  watchDirectory: dir => ipcRenderer.invoke('haishui:watchDirectory', dir),
  stopPreviewFileWatch: id => ipcRenderer.invoke('haishui:stopPreviewFileWatch', id),
  setActiveWork: payload => ipcRenderer.send('haishui:active-work', payload),
  setTitleBarTheme: payload => ipcRenderer.send('haishui:titlebar-theme', payload),
  setNativeTheme: mode => ipcRenderer.send('haishui:native-theme', mode),
  setTranslucency: payload => ipcRenderer.send('haishui:translucency', payload),
  setKeepAwake: on => ipcRenderer.send('haishui:keep-awake', on),
  setDisableF12: blocked => ipcRenderer.send('haishui:devtools:disable-f12', blocked),
  setPreviewShortcutActive: active => ipcRenderer.send('haishui:previewShortcutActive', Boolean(active)),
  openExternal: url => ipcRenderer.invoke('haishui:openExternal', url),
  mcpOauth: {
    // One-shot loopback listener for MCP OAuth against remote backends: bind
    // on this machine, hand redirectUri to mcp.servers.oauth.start, then wait
    // for the provider redirect and relay code/state via oauth.callback.
    listen: () => ipcRenderer.invoke('haishui:mcp-oauth:listen'),
    wait: (id, timeoutMs) => ipcRenderer.invoke('haishui:mcp-oauth:wait', id, timeoutMs),
    cancel: id => ipcRenderer.invoke('haishui:mcp-oauth:cancel', id)
  },
  openPreviewInBrowser: url => ipcRenderer.invoke('haishui:openPreviewInBrowser', url),
  reachPreviewUrl: url => ipcRenderer.invoke('haishui:preview:reach', url),
  setActiveConnectionRoute: route => ipcRenderer.send('haishui:connection:active-route', route),
  fetchLinkTitle: url => ipcRenderer.invoke('haishui:fetchLinkTitle', url),
  resolveFavicon: url => ipcRenderer.invoke('haishui:resolveFavicon', url),
  sanitizeWorkspaceCwd: cwd => ipcRenderer.invoke('haishui:workspace:sanitize', cwd),
  settings: {
    getDefaultProjectDir: () => ipcRenderer.invoke('haishui:setting:defaultProjectDir:get'),
    setDefaultProjectDir: dir => ipcRenderer.invoke('haishui:setting:defaultProjectDir:set', dir),
    pickDefaultProjectDir: () => ipcRenderer.invoke('haishui:setting:defaultProjectDir:pick')
  },
  zoom: {
    // Current zoom of this window, as { level, percent }.
    get: () => ipcRenderer.invoke('haishui:zoom:get'),
    // Synchronous zoom factor (1 = 100%). Coordinate math needs it in the
    // same tick as the event it converts, so no IPC round-trip here.
    factor: () => webFrame.getZoomFactor(),
    setPercent: percent => ipcRenderer.send('haishui:zoom:set-percent', percent),
    // Fires on every zoom change, including the Ctrl/Cmd +/-/0 shortcuts,
    // so the settings UI can stay in sync with the keyboard.
    onChanged: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('haishui:zoom:changed', listener)

      return () => ipcRenderer.removeListener('haishui:zoom:changed', listener)
    }
  },
  revealLogs: () => ipcRenderer.invoke('haishui:logs:reveal'),
  getRecentLogs: () => ipcRenderer.invoke('haishui:logs:recent'),
  // Fire-and-forget: persists a renderer error-boundary catch (with component
  // stack) to desktop.log so crashes survive the window (#79428).
  reportRendererError: report => ipcRenderer.send('haishui:logs:renderer-error', report),
  readDir: dirPath => ipcRenderer.invoke('haishui:fs:readDir', dirPath),
  gitRoot: startPath => ipcRenderer.invoke('haishui:fs:gitRoot', startPath),
  revealPath: targetPath => ipcRenderer.invoke('haishui:fs:reveal', targetPath),
  openDir: dirPath => ipcRenderer.invoke('haishui:fs:openDir', dirPath),
  desktopPluginsRoot: () => ipcRenderer.invoke('haishui:fs:desktopPluginsRoot'),
  reconcileDesktopPlugins: () => ipcRenderer.invoke('haishui:fs:reconcileDesktopPlugins'),
  logsRoot: () => ipcRenderer.invoke('haishui:fs:logsRoot'),
  renamePath: (targetPath, newName) => ipcRenderer.invoke('haishui:fs:rename', targetPath, newName),
  writeTextFile: (filePath, content) => ipcRenderer.invoke('haishui:fs:writeText', filePath, content),
  trashPath: targetPath => ipcRenderer.invoke('haishui:fs:trash', targetPath),
  git: {
    worktreeList: repoPath => ipcRenderer.invoke('haishui:git:worktreeList', repoPath),
    worktreeAdd: (repoPath, options) => ipcRenderer.invoke('haishui:git:worktreeAdd', repoPath, options),
    worktreeRemove: (repoPath, worktreePath, options) =>
      ipcRenderer.invoke('haishui:git:worktreeRemove', repoPath, worktreePath, options),
    branchSwitch: (repoPath, branch) => ipcRenderer.invoke('haishui:git:branchSwitch', repoPath, branch),
    branchList: repoPath => ipcRenderer.invoke('haishui:git:branchList', repoPath),
    baseBranchList: repoPath => ipcRenderer.invoke('haishui:git:baseBranchList', repoPath),
    repoStatus: repoPath => ipcRenderer.invoke('haishui:git:repoStatus', repoPath),
    fileDiff: (repoPath, filePath) => ipcRenderer.invoke('haishui:git:fileDiff', repoPath, filePath),
    scanRepos: (roots, options) => ipcRenderer.invoke('haishui:git:scanRepos', roots, options),
    review: {
      list: (repoPath, scope, baseRef) => ipcRenderer.invoke('haishui:git:review:list', repoPath, scope, baseRef),
      diff: (repoPath, filePath, scope, baseRef, staged) =>
        ipcRenderer.invoke('haishui:git:review:diff', repoPath, filePath, scope, baseRef, staged),
      stage: (repoPath, filePath) => ipcRenderer.invoke('haishui:git:review:stage', repoPath, filePath),
      unstage: (repoPath, filePath) => ipcRenderer.invoke('haishui:git:review:unstage', repoPath, filePath),
      revert: (repoPath, filePath) => ipcRenderer.invoke('haishui:git:review:revert', repoPath, filePath),
      revParse: (repoPath, ref) => ipcRenderer.invoke('haishui:git:review:revParse', repoPath, ref),
      commit: (repoPath, message, push) => ipcRenderer.invoke('haishui:git:review:commit', repoPath, message, push),
      commitContext: repoPath => ipcRenderer.invoke('haishui:git:review:commitContext', repoPath),
      push: repoPath => ipcRenderer.invoke('haishui:git:review:push', repoPath),
      shipInfo: repoPath => ipcRenderer.invoke('haishui:git:review:shipInfo', repoPath),
      prList: (repoPath, branches, numbers) =>
        ipcRenderer.invoke('haishui:git:review:prList', repoPath, branches, numbers),
      createPr: repoPath => ipcRenderer.invoke('haishui:git:review:createPr', repoPath)
    }
  },
  terminal: {
    attach: id => ipcRenderer.invoke('haishui:terminal:attach', id),
    cwd: id => ipcRenderer.invoke('haishui:terminal:cwd', id),
    dispose: id => ipcRenderer.invoke('haishui:terminal:dispose', id),
    resize: (id, size) => ipcRenderer.invoke('haishui:terminal:resize', id, size),
    start: options => ipcRenderer.invoke('haishui:terminal:start', options),
    write: (id, data) => ipcRenderer.invoke('haishui:terminal:write', id, data),
    onData: (id, callback) => {
      const channel = `haishui:terminal:${id}:data`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)
    },
    onExit: (id, callback) => {
      const channel = `haishui:terminal:${id}:exit`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)
    }
  },
  onClosePreviewRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('haishui:close-preview-requested', listener)

    return () => ipcRenderer.removeListener('haishui:close-preview-requested', listener)
  },
  onPreviewNav: callback => {
    const listener = (_event, command) => callback(command)
    ipcRenderer.on('haishui:preview-nav', listener)

    return () => ipcRenderer.removeListener('haishui:preview-nav', listener)
  },
  onOpenFolderRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('haishui:open-folder-requested', listener)

    return () => ipcRenderer.removeListener('haishui:open-folder-requested', listener)
  },
  onOpenUpdatesRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('haishui:open-updates', listener)

    return () => ipcRenderer.removeListener('haishui:open-updates', listener)
  },
  onDeepLink: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('haishui:deep-link', listener)

    return () => ipcRenderer.removeListener('haishui:deep-link', listener)
  },
  signalDeepLinkReady: () => ipcRenderer.invoke('haishui:deep-link-ready'),
  probePluginRepo: payload => ipcRenderer.invoke('haishui:plugin:probe', payload),
  installDesktopPlugin: payload => ipcRenderer.invoke('haishui:plugin:installDesktop', payload),
  onWindowStateChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('haishui:window-state-changed', listener)

    return () => ipcRenderer.removeListener('haishui:window-state-changed', listener)
  },
  onFocusSession: callback => {
    const listener = (_event, sessionId) => callback(sessionId)
    ipcRenderer.on('haishui:focus-session', listener)

    return () => ipcRenderer.removeListener('haishui:focus-session', listener)
  },
  onNotificationAction: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('haishui:notification-action', listener)

    return () => ipcRenderer.removeListener('haishui:notification-action', listener)
  },
  onNotificationActivate: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('haishui:notification-activate', listener)

    return () => ipcRenderer.removeListener('haishui:notification-activate', listener)
  },
  onPreviewFileChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('haishui:preview-file-changed', listener)

    return () => ipcRenderer.removeListener('haishui:preview-file-changed', listener)
  },
  onBackendExit: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('haishui:backend-exit', listener)

    return () => ipcRenderer.removeListener('haishui:backend-exit', listener)
  },
  // Cooperative pool retirement (main → renderer): the pooled backend under
  // `poolKey` is being stopped for a foreground open. Park that scope; do not
  // redial into the slot it vacated.
  onPoolBackendRetiring: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('haishui:pool:retiring', listener)

    return () => ipcRenderer.removeListener('haishui:pool:retiring', listener)
  },
  // Soft gateway-mode apply finished tearing down the primary backend. Renderer
  // should wipe session lists + re-dial without a window reload.
  onConnectionApplied: callback => {
    const listener = () => callback()
    ipcRenderer.on('haishui:connection:applied', listener)

    return () => ipcRenderer.removeListener('haishui:connection:applied', listener)
  },
  onPowerResume: callback => {
    const listener = () => callback()
    ipcRenderer.on('haishui:power-resume', listener)

    return () => ipcRenderer.removeListener('haishui:power-resume', listener)
  },
  // AC ↔ battery transitions; renderers slow their backstop polls on battery.
  getOnBattery: () => ipcRenderer.invoke('haishui:power-battery:get'),
  onBatteryChanged: callback => {
    const listener = (_event, onBattery) => callback(Boolean(onBattery))
    ipcRenderer.on('haishui:power-battery', listener)

    return () => ipcRenderer.removeListener('haishui:power-battery', listener)
  },
  onBootProgress: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('haishui:boot-progress', listener)

    return () => ipcRenderer.removeListener('haishui:boot-progress', listener)
  },
  // First-launch bootstrap progress -- emitted by the install.ps1 stage
  // runner in main.ts (apps/desktop/electron/bootstrap-runner.ts).
  // Renderer's install overlay subscribes to live events and queries the
  // current snapshot via getBootstrapState() to recover after a devtools
  // reload mid-bootstrap.
  getBootstrapState: () => ipcRenderer.invoke('haishui:bootstrap:get'),
  continueBootstrapLocal: () => ipcRenderer.invoke('haishui:bootstrap:continue-local'),
  recycleBackend: profile => ipcRenderer.invoke('haishui:backend:recycle', profile),
  resetBootstrap: () => ipcRenderer.invoke('haishui:bootstrap:reset'),
  repairBootstrap: () => ipcRenderer.invoke('haishui:bootstrap:repair'),
  cancelBootstrap: () => ipcRenderer.invoke('haishui:bootstrap:cancel'),
  onBootstrapEvent: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('haishui:bootstrap:event', listener)

    return () => ipcRenderer.removeListener('haishui:bootstrap:event', listener)
  },
  getVersion: () => ipcRenderer.invoke('haishui:version'),
  relaunchApp: () => ipcRenderer.invoke('haishui:app:relaunch'),
  getMachineProfile: () => ipcRenderer.invoke('haishui:machine:profile'),
  getRemoteDisplayReason: () => ipcRenderer.invoke('haishui:get-remote-display-reason'),
  uninstall: {
    summary: () => ipcRenderer.invoke('haishui:uninstall:summary'),
    run: mode => ipcRenderer.invoke('haishui:uninstall:run', { mode })
  },
  updates: {
    check: opts => ipcRenderer.invoke('haishui:updates:check', opts),
    apply: opts => ipcRenderer.invoke('haishui:updates:apply', opts),
    getBranch: () => ipcRenderer.invoke('haishui:updates:branch:get'),
    setBranch: name => ipcRenderer.invoke('haishui:updates:branch:set', name),
    onProgress: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('haishui:updates:progress', listener)

      return () => ipcRenderer.removeListener('haishui:updates:progress', listener)
    }
  },
  themes: {
    fetchMarketplace: id => ipcRenderer.invoke('haishui:vscode-theme:fetch', id),
    searchMarketplace: query => ipcRenderer.invoke('haishui:vscode-theme:search', query)
  },
  // Find-in-page (Ctrl/Cmd+F): delegates to Electron's
  // webContents.findInPage on the IPC sender's window so a Cmd+F pressed
  // in a secondary session window searches THAT window, not the primary.
  // `onFoundInPage` returns the unsubscribe fn; the renderer wires it via
  // `initFindInPageListener` in store/find-in-page.ts and tears it down
  // when the FindBar unmounts.
  findInPage: (query, options) => ipcRenderer.invoke('haishui:find-in-page', query, options),
  stopFindInPage: () => ipcRenderer.invoke('haishui:stop-find-in-page'),
  onFoundInPage: callback => {
    const listener = (_event, result) => callback(result)
    ipcRenderer.on('haishui:found-in-page', listener)

    return () => ipcRenderer.removeListener('haishui:found-in-page', listener)
  },
  // Main-process `before-input-event` forwards Ctrl/Cmd+F here so renderer
  // can open the FindBar even when the GTK compositor has already grabbed
  // the chord at the windowing layer (#81727).
  onOpenFindBarRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('haishui:open-find-bar', listener)

    return () => ipcRenderer.removeListener('haishui:open-find-bar', listener)
  }
})
