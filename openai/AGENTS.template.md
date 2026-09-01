Before work, read `.roblox-harness/shared/CORE.md`; it defines project working
rules at their configured dispositions.

First setup: trust this project; review and approve its hooks; run
`python3 .roblox-harness/openai/setup/permissions_harness.py --install`; select the
Roblox permission preset; start a new session. Untrusted projects and changed,
unapproved hooks do not pass the project gate.

When the current operation consumes Studio, DataModel, console, or live-place
facts, list Studios with native Roblox Studio MCP, select one, and execute
`return game.PlaceId` in Edit mode. Continue only if that PlaceId is in
`## places`; otherwise report the required connection or place decision and
stop. Read-only and mechanical work that consumes no live fact does not
require Studio.

After changes and review are settled, run the exact pre-final validation
command supplied by `UserPromptSubmit` as the last tool before the final
response. `Stop` verifies only its settled-state receipt.

## summary

{{SUMMARY}}

## places

{{PLACES}}
