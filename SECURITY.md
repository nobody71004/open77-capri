# Security

## Server

- The clinic installer does **not** change `server.jsonc` and does **not** set
  `"unsecured": true`. Keep authentication enabled and put any unsecured
  listener behind a private network, firewall or VPN.
- Run installers as root only on the intended server, after taking a backup.
- The package-split reference scripts delete old `.open77/mods/*.blob` files.
  Review the constants, keep the generated backup directory, and test staging
  before production.
- Never commit `.env`, SSH keys, database passwords, API keys, server IPs or
  player data. `.gitignore` excludes the common cases, but check
  `git diff --cached` before every push.

## Client

- Capri's `settings.json` and CapriVoz configuration can contain provider keys.
  Keep them local and out of version control.
- The optional MCP bridge only listens on local files and drives the public
  Capri API; it does not read provider keys. The optional brain server binds to
  `127.0.0.1` by default and should not be exposed to a network.
- The MCP shell/computer-use tools are powerful. Restrict their roots and only
  enable them for a trusted local operator.
- Capri's microphone and screen features are local capabilities. Do not enable
  them for an untrusted client or stream.

## Reporting

This is a fan integration patch set. Report security issues privately to the
repository owner rather than opening a public issue containing credentials or
server addresses.
