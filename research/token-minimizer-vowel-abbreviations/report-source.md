# Vowel-stripped word candidates for the token minimizer

Audience: harness maintainers  
Date: 2026-08-29  
Scope: English prose in game, general, software, and programming records. Code, names, quoted text, schema fields, and spoken output are excluded.

## Direct answer

Do not add a general vowel-removal rule.

For the current `o200k_base` token minimizer, approve only this word mapping:

| Scope | Full word | Short form | Ordinary word-boundary tokens | Decision |
|---|---|---:|---:|---|
| Game prose only | dexterity | `dex` | 2 -> 1 | Approve |

The other readable forms below are a review pool. They shorten characters, but they do not reduce `o200k_base` tokens at an ordinary space boundary. Do not put them in the active token allowlist without a corpus measurement that shows a net reduction.

## Evidence and test result

Vowel deletion is a common abbreviation method. In a 150,000-example abbreviation data set, vowel-deletion methods accounted for 68.3% of the examples. The same research treats expansion as a context-dependent task and does not assume that a short form has one dictionary expansion ([Gorman et al., 2021](https://aclanthology.org/2021.findings-emnlp.85.pdf)).

This context requirement agrees with the Microsoft rule to use only abbreviations that the audience knows. Microsoft also warns that abbreviations can reduce clarity and findability ([Microsoft Style Guide](https://learn.microsoft.com/en-us/style-guide/acronyms)).

The local minimizer requires each replacement to save at least one `o200k_base` token and rejects edits with more than one plausible meaning ([token_shrink.py](../../shared/gates/token_shrink.py), [token_shrink_corpus.json](../../tools/tests/token_shrink_corpus.json)).

I tested 277 candidate mappings with tiktoken 0.14.0, the `o200k_base` encoding, and an ordinary leading-space word boundary:

| Result | Candidate count |
|---|---:|
| Reduced tokens | 3 |
| Same token count | 171 |
| Increased tokens | 103 |

The three reductions were `dexterity -> dex`, `singleplayer -> sp`, and `nonplayer -> npc`. Reject the last two: `SP` has several common game meanings, and `NPC` expands to “nonplayer character,” not “nonplayer.” This leaves one semantically safe, token-reducing word mapping.

This result is expected for byte-pair encoding. Common full words and common subwords often already use one token. Removing letters can create an uncommon string that uses more tokens ([OpenAI tiktoken README](https://github.com/openai/tiktoken/blob/main/README.md)).

## Review pool: readable forms

These forms are candidates for character minimization or a custom dictionary. They are not approved for the current token allowlist.

### General words

| Full word | Short form | Full word | Short form |
|---|---:|---|---:|
| information | `info` | approximately | `approx` |
| maximum | `max` | minimum | `min` |
| message | `msg` | number | `num` |
| quantity | `qty` | amount | `amt` |
| average | `avg` | example | `ex` |
| reference | `ref` | total | `ttl` |
| count | `cnt` | hour | `hr` |
| second | `sec` | year | `yr` |
| week | `wk` | type | `typ` |
| size | `sz` | group | `grp` |

Use `min`, `sec`, `ref`, and `ex` only in typed fields. Each form has more than one common expansion.

### Game terms

| Full term | Short form | Full term | Short form |
|---|---:|---|---:|
| level | `lvl` | damage | `dmg` |
| attack | `atk` | defense | `def` |
| strength | `str` | dexterity | `dex` |
| intelligence | `int` | character | `char` |
| inventory | `inv` | experience points | `XP` |
| hit points | `HP` | cooldown | `CD` |
| critical | `crit` | position | `pos` |
| velocity | `vel` | animation | `anim` |
| camera | `cam` | controller | `ctrl` |
| multiplayer | `MP` | single-player | `SP` |
| nonplayer character | `NPC` | difficulty | `diff` |
| objective | `obj` | physics | `phys` |
| sound | `snd` | damage per second | `DPS` |

An official game glossary uses `Dex.`, `HP`, `NPC`, `Str.`, and `XP`, which supports recognition inside game context ([D&D Beyond rules glossary](https://www.dndbeyond.com/sources/dnd/br-2024/rules-glossary/)). The forms `str`, `int`, `char`, `pos`, `SP`, and `CD` are not safe outside a game-specific field.

### Software terms

| Full word | Short form | Full word | Short form |
|---|---:|---|---:|
| configuration | `config` | development | `dev` |
| production | `prod` | temporary | `tmp` |
| repository | `repo` | package | `pkg` |
| dependency | `dep` | version | `ver` |
| command | `cmd` | database | `db` |
| document | `doc` | application | `app` |
| message | `msg` | error | `err` |
| network | `net` | address | `addr` |
| connection | `conn` | protocol | `proto` |
| authentication | `auth` | asynchronous | `async` |
| synchronous | `sync` | initialization | `init` |
| implementation | `impl` | environment | `env` |
| directory | `dir` | source | `src` |
| destination | `dst` | request | `req` |
| response | `resp` | library | `lib` |
| binary | `bin` | executable | `exe` |
| system | `sys` | process | `proc` |
| memory | `mem` | buffer | `buf` |

### Programming terms

| Full word | Short form | Full word | Short form |
|---|---:|---|---:|
| function | `fn` | variable | `var` |
| parameter | `param` | argument | `arg` |
| string | `str` | boolean | `bool` |
| integer | `int` | number | `num` |
| object | `obj` | array | `arr` |
| dictionary | `dict` | return | `ret` |
| value | `val` | event | `evt` |
| context | `ctx` | optional | `opt` |
| update | `upd` | delete | `del` |
| execute | `exec` | debug | `dbg` |
| constant | `const` | mutable | `mut` |
| public | `pub` | private | `priv` |
| structure | `struct` | enumeration | `enum` |
| iterator | `iter` | exception | `exc` |
| expression | `expr` | statement | `stmt` |
| condition | `cond` | index | `idx` |
| length | `len` | pointer | `ptr` |
| namespace | `ns` | attribute | `attr` |
| constructor | `ctor` | initialize | `init` |
| increment | `inc` | decrement | `dec` |
| compare | `cmp` | format | `fmt` |

Official language documentation supports several of these forms. Rust uses `fn`, `impl`, `mut`, `pub`, `struct`, and `enum` as language terms ([Rust keywords](https://doc.rust-lang.org/stable/book/appendix-01-keywords.html)). Python uses `str`, `bool`, `int`, and `dict` as built-in type names ([Python built-in types](https://docs.python.org/3/library/stdtypes.html)). These forms are recognizable to programmers, but that does not make them token-saving replacements.

## Reject list

Reject these full vowel skeletons. Each increased the ordinary-boundary token count or created material ambiguity.

| Category | Reject mappings |
|---|---|
| General | `thanks -> thnks`, `section -> sctn`, `question -> qstn`, `description -> dscrptn`, `condition -> cndtn`, `problem -> prblm`, `solution -> sltn`, `available -> avlbl` |
| Game | `player -> plyr`, `enemy -> enmy`, `quest -> qst`, `reward -> rwrd`, `health -> hlth`, `stamina -> stmn`, `armor -> armr`, `weapon -> wpn`, `skill -> skll`, `target -> trgt` |
| Software | `client -> clnt`, `authorization -> authz`, `runtime -> rntm`, `compiler -> cmplr`, `debugger -> dbggr`, `commit -> cmt`, `storage -> strg`, `container -> cntnr` |
| Programming | `result -> rslt`, `default -> dflt`, `required -> reqd`, `thread -> thrd`, `compile -> cmpl`, `enable -> enbl`, `disable -> dsbl`, `method -> mthd`, `validate -> vld` |

## Limitations

The token result applies to tiktoken 0.14.0, `o200k_base`, lowercase source words, and the tested boundaries. Capitalization, punctuation, inflection, and a different encoding can change the count. Recognition judgments apply to English-speaking game and software audiences. They do not establish accessibility or text-to-speech safety.

## Claim-to-source ledger

| Claim | Source | Date | Access note |
|---|---|---|---|
| Vowel deletion represented 68.3% of the study data; expansion used context | “Structured abbreviation expansion in context,” Gorman et al., ACL | 2021-11 | PDF and paper page accessed 2026-08-29 |
| Use only audience-familiar abbreviations | “Acronyms,” Microsoft Style Guide | Updated 2024-08-26 | Web page accessed 2026-08-29 |
| `Dex.`, `HP`, `NPC`, `Str.`, and `XP` are official game abbreviations | “Rules Glossary,” D&D Beyond | 2024 rules | Web page accessed 2026-08-29 |
| `fn`, `impl`, `mut`, `pub`, `struct`, and `enum` are established language terms | “Appendix A: Keywords,” The Rust Programming Language | Current stable documentation | Web page accessed 2026-08-29 |
| `str`, `bool`, `int`, and `dict` are established built-in type names | “Built-in Types,” Python 3.14.6 documentation | Current documentation | Web page accessed 2026-08-29 |
| Character reduction does not guarantee BPE token reduction | tiktoken README, OpenAI | Current main branch | Web page accessed 2026-08-29 |
| Local minimizer uses measured `o200k_base` contractions and rejects ambiguity | `shared/gates/token_shrink.py`; `tools/tests/token_shrink_corpus.json` | Current workspace | Read locally 2026-08-29 |
