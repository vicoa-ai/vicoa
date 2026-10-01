---
name: live-preview
description: Start a local app in the current user project, expose it through a tunnel, and return preview details in structured Markdown. Use when the user asks for a preview URL, public URL, shareable localhost, mobile/web preview, or tunnel setup.
argument-hint: "[optional: run command | port | provider]"
disable-model-invocation: true
allowed-tools: Read, Glob, Grep, LS, Bash
---

Create and report a live preview endpoint for the current repository.

Use arguments:
- Raw arguments: `$ARGUMENTS`
- First argument: `$0`
- Second argument: `$1`

Follow this workflow.

## 1) Resolve runtime plan
- Prefer explicit user arguments for run command, port, and tunnel provider.
- Otherwise infer a dev/start command from project files (e.g., `package.json`, `pyproject.toml`, `requirements.txt`, `Cargo.toml`, `go.mod`) and repository docs.
- Prefer loopback bind target (`127.0.0.1`).

## 2) Handle local port and app process
- Before starting a new service, check whether the target port is already in use.
- If port is free, start the app in background and capture PID.
- If port is occupied, inspect the owning process command/cwd.
- If the process appears to be the same project and same service (matching repository path and compatible run command), reuse that existing service and keep the same port.
- If the process is different (other project or different service), choose one alternate port and start a new service once.
- Include in `message` whether the preview reused an existing service or started a new one.

## 3) Verify local readiness
- Probe `http://127.0.0.1:<port>` for up to 60 seconds.
- Treat any HTTP response as reachable preview surface.
- If unreachable, return an error result in the structured Markdown format.

## 4) Start tunnel
- Try Cloudflare first: `cloudflared tunnel --url http://127.0.0.1:<port>`.
- Parse `https://*.trycloudflare.com` from output.
- If unavailable or failed, try ngrok (`ngrok http <port>`) and read URL from `http://127.0.0.1:4040/api/tunnels`.
- If both fail due to cloudflare or ngrok not installed, install them and try again. 
- If tunnel setup fails, return an error result that includes a concrete install/action hint.

## 5) Emit structured Markdown result
- Print final output as Markdown bullets only, with `*` at the beginning of each line.
- Extract the tunnel URL from provider output and include it as `public_url`.
- Include exactly these fields, one per line:
* status: ok or error
* provider: cloudflare, ngrok, or none
* local_url: local URL such as http://127.0.0.1:3000
* port: numeric local port
* pid: process id or null
* message: short actionable summary
* public_url: tunnel URL or null
- Do not print secrets.
- Keep `message` concise and actionable.

## 6) Keep lifecycle predictable
- Keep preview processes running unless the user asked for one-shot verification only.
- If user asked to stop/cleanup, terminate local app and tunnel processes and return success result in the same structured Markdown format.
