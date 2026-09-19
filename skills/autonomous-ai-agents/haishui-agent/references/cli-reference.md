# Haishui CLI Reference

Live sources when anything looks stale: `haishui --help`, `haishui <command> --help`,
https://aiqinghaiwork163.github.io/haishui-agent/docs/reference/cli-commands

### Global Flags

```
haishui [flags] [command]        (no subcommand = interactive chat)

  --version, -V             Show version
  -z, --oneshot PROMPT      One-shot: print ONLY the final response (for scripts/pipes)
  -m MODEL  --provider P    Model/provider override for this invocation
  -t, --toolsets LIST       Comma-separated toolsets for this invocation
  --resume, -r SESSION      Resume session by ID or title
  --continue, -c [NAME]     Resume by name, or most recent session
  --worktree, -w            Isolated git worktree mode (parallel agents)
  --skills, -s SKILL        Preload skills (comma-separate or repeat)
  --profile, -p NAME        Use a named profile
  --yolo                    Skip dangerous command approval
  --tui / --cli             Force the Ink TUI / classic REPL
  --ignore-rules            Skip AGENTS.md/SOUL.md/memory/skill injection
  --safe-mode               Disable ALL customizations (troubleshooting)
  --pass-session-id         Include session ID in system prompt
```

### Chat

```
haishui chat [flags]
  -q, --query TEXT          Single query, non-interactive
  --image PATH              Attach a local image to a single query
  -Q, --quiet               Suppress banner, spinner, tool previews
  --checkpoints             Enable filesystem checkpoints (/rollback)
  --max-turns N             Cap tool-calling iterations
  --source TAG              Session source tag (default: cli)
```
(plus the global flags above)

### Configuration

```
haishui setup [section]      Wizard (model|tts|terminal|gateway|tools|agent)
haishui model                Interactive model/provider picker
haishui fallback [add|remove|list]  Fallback provider chain
haishui config [show|edit|get|set|unset|path|env-path|check|migrate]
haishui login / logout       OAuth sign-in / clear stored auth
haishui doctor [--fix]       Check dependencies and config
haishui status [--all]       Component status
```

### Tools & Skills

```
haishui tools [list|enable NAME|disable NAME]   Per-platform toolsets (curses UI with no args)

haishui skills list|browse|search QUERY|inspect ID
haishui skills install ID    Hub identifier OR a direct https://…/SKILL.md URL
haishui skills config        Enable/disable skills per platform
haishui skills check|update|uninstall|publish PATH
haishui skills tap add REPO  Add a GitHub repo as a skill source
haishui bundles              Skill bundles (one /<name> alias loads several skills)
```

### MCP Servers

```
haishui mcp add NAME (--url or --command) | remove | list | test NAME
haishui mcp catalog | install NAME     Curated catalog install
haishui mcp configure NAME             Toggle tool selection
haishui mcp serve                      Run Haishui as an MCP server
```
Details (transport, tool discovery, catalog): `references/native-mcp.md`.

### Gateway (Messaging Platforms)

```
haishui gateway run|install|start|stop|restart|status|setup
```

20+ platforms: Telegram, Discord, Slack, WhatsApp (Baileys + Business Cloud API), iMessage (Photon — `haishui photon setup`), Signal, Email, SMS, Matrix, Mattermost, Teams, LINE, SimpleX, ntfy, Google Chat, Home Assistant, DingTalk, Feishu, WeCom, Weixin, API Server, Webhooks. Open WebUI connects via the API Server adapter. Most adapters ship under `plugins/platforms/`.
Docs: https://aiqinghaiwork163.github.io/haishui-agent/docs/user-guide/messaging/

### Sessions

```
haishui sessions list|browse|rename ID TITLE|delete ID|export OUT|prune|stats
```

### Cron / Webhooks

```
haishui cron list|create SCHED|edit ID|pause|resume|run ID|remove|status
    Schedules: '30m', 'every 2h', '0 9 * * *', ISO timestamp
haishui webhook subscribe NAME|list|remove NAME|test NAME
```
Webhook payloads/routes: `references/webhooks.md`.

### Profiles

```
haishui profile list|create NAME (--clone|--clone-all|--clone-from)|use|show|delete
haishui profile rename A B | alias NAME | export NAME | import FILE
haishui profile migrate-identity A B   Retry a completed rename's session/routing identity migration
```

### Credentials & Pools

```
haishui auth                 Interactive credential manager
haishui auth add [PROVIDER]  Add OAuth or API-key credential (nous, openai-codex, qwen-oauth, …)
haishui auth list|remove P IDX|reset PROVIDER|status
```
Multiple credentials per provider form a pool that rotates automatically and skips exhausted keys.

### Other

```
haishui desktop / gui        Native desktop app
haishui dashboard            Web admin panel + embedded chat (--stop / --status)
haishui proxy                OpenAI-compatible local proxy backed by an OAuth provider
haishui portal               Quick setup / sign in via Nous Portal
haishui kanban <verb>        Multi-agent work-queue board
haishui project              Named multi-folder workspaces
haishui skin list|use|set    Switch/tweak skins (see references/themes.md)
haishui pets <verb>          Pet mascots (see references/petdex.md)
haishui memory setup|status|off|reset   Memory provider
haishui secrets bitwarden|onepassword   External secret stores
haishui moa                  Mixture-of-Agents slots
haishui hooks / security / backup / import / checkpoints / console
haishui logs [-f] [errors]   View agent/error logs
haishui send                 One-off message through a gateway platform
haishui pairing / plugins / insights / journey / computer-use
haishui acp                  ACP server (IDE integration)
haishui completion bash|zsh|fish
haishui update / uninstall / claw migrate
```

Plugin- and provider-supplied subcommands (e.g. `haishui photon setup`) only appear once their plugin is installed/active.

### Where to Find Things

| Looking for... | Location |
|---|---|
| Config options | `haishui config edit` · [Configuration docs](https://aiqinghaiwork163.github.io/haishui-agent/docs/user-guide/configuration) |
| Tools / toolsets | `haishui tools list` · [Tools reference](https://aiqinghaiwork163.github.io/haishui-agent/docs/reference/tools-reference) |
| Skills catalog | `haishui skills browse` · [Skills catalog](https://aiqinghaiwork163.github.io/haishui-agent/docs/reference/skills-catalog) |
| Provider setup | `haishui model` · [Providers guide](https://aiqinghaiwork163.github.io/haishui-agent/docs/integrations/providers) |
| Env variables | `haishui config env-path` · [Env vars reference](https://aiqinghaiwork163.github.io/haishui-agent/docs/reference/environment-variables) |
| Gateway logs | `~/.haishui/logs/gateway.log` (or `haishui logs`) |
| Sessions | `haishui sessions browse` (reads state.db) |
