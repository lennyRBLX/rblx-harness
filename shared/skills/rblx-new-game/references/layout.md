# Setup choices

- Fields: `gameplay`, `places`, `services`, `controllers`, `assets`, `harness`.
- Services/Controllers: `shared: Name, Name; Place: Name` or `none`. New names
  are bare PascalCase nouns, letters/digits, starting with a letter; no
  Service/Controller suffix. Propose detected modules first; exclude harness assets.
- Assets: `packages`, `services`, `controllers`, `plugins`; `all` selects all four.
  Only plugins can stand alone. Keep existing `plugins/`. Accepted detected modules
  replace destination boilerplate byte-for-byte. Root `manifest.json` stores choices.
- Keep bootstrap `rblx-new-game` external. Ignore generated
  `.agents/`, `.codex/`, `.roblox` and Serena-owned `.serena/`. Install no harness hooks.
  Preserve project docs and unrelated user configuration.
