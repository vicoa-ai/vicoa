# Output Format

Return the final result as Markdown bullets only, one line per field, each line starting with *.

Required fields:

- status: ok or error
- provider: cloudflare, ngrok, or none
- local_url: local URL such as http://127.0.0.1:3000
- port: numeric local port
- pid: process id or null
- message: short actionable summary
- public_url: tunnel URL or null

Notes:
- Keep field names stable for downstream parsing.
- Do not print secrets.
- Ensure public_url is extracted from tunnel output.
