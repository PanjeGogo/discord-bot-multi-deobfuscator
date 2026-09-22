# Lua Deobfuscator Discord Bot — Gemini + Pterodactyl

- `!deobfus` + attachment `.lua`
- Local obfuscator fingerprinting
- Iterative Gemini deobfuscation
- Persistent `temp/progress.json` and `temp/jobs/<job_id>/`
- Per-pass checkpoints
- Resume-ready state files
- `🛑 Batalkan` button on the process embed
- Cancel button usable only by the original uploader or a server Administrator
- Cancellation stops the running task and prevents further Gemini passes
- Logs in `temp/logs/bot.log`
- No Lua execution

Pterodactyl:
1. Extract ZIP.
2. Copy `.env.example` to `.env`.
3. Fill `DISCORD_TOKEN` and `GEMINI_API_KEY`.
4. `pip install -r requirements.txt`
5. `bash start.sh`

Gemini API quotas/rate limits still apply.
