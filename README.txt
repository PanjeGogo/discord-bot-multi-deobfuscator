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


## Local Luraph engine

The bot now runs `engines/luraph_vm.py` before Gemini for the Luraph v14 profile.
It is deliberately non-executing: it performs bounded constant folding/string
concatenation and records VM-like instruction indicators. If it changes the
source, the bot checkpoints that result and skips the Gemini request for that
pass.

This is the safe first layer of the planned Luraph VM emulator. A full
Luau/Roblox runtime is intentionally not embedded because executing arbitrary
uploaded Lua/Luau would defeat the bot's sandbox boundary.
