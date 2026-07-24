<h1 align="center">@Mention Replacement</h1>

<p align="center">
  Automatically replace casual nicknames and transliterated names in transcripts<br>
  with the canonical spelling you want.<br>
  e.g. speech "艾特小明" (at Xiaoming) →  transcribed & replaced as <code>@Xiaoming</code>
</p>

<p align="center">
  <b>English</b> | <a href="README_zh.md">中文</a>
</p>

<p align="center">
  <a href="#-overview">Overview</a> ·
  <a href="#-quick-start">Quick Start</a> ·
  <a href="#-how-it-works">How It Works</a> ·
  <a href="#-editing-config-manually">Manual Editing</a> ·
  <a href="#-developer-api">Developer API</a> ·
  <a href="#-faq">FAQ</a>
</p>

---

## 📖 Overview

When transcribing, ASR often outputs names and English proper nouns as transliterations or in inconsistent spellings, and it cannot recognize internal team nicknames.

The **mention feature** runs a post-processing pass after transcription: it scans the text for `@mentions` and replaces aliases with their canonical names according to a mapping table.

Replacements come from three layers, merged from **lowest to highest priority** (later layers override earlier ones on conflict):

| Priority | Source | File | Use case |
| :---: | :--- | :--- | :--- |
| Low | Built-in | code constant `MENTION_MAP` | Preset common transliterated names |
| Medium | OpenClaw | `~/.octoasr/mentions/openclaw.json` | One canonical name, multiple aliases |
| **High** | **User table** | `~/.octoasr/mentions/user.json` | **Custom nicknames, most common** |

> 💡 Config files are **created automatically as empty templates on first use** — no need to create the directory manually.

---

## 🚀 Quick Start

> For all users — **no need to edit any JSON file**.

**1. Start the service and open the management page**

```bash
octoasr start        # Start the service (if not running)
octoasr mentions     # Open the entry management page automatically
```

Your browser opens the management page at `http://127.0.0.1:<port>/mentions`.

**2. Manage entries on the page**

| Action | Steps |
| :--- | :--- |
| ➕ Add | Enter **Nickname** and **Canonical name**, click **Add** |
| ✏️ Edit | Click **Edit** on a row, modify inline, click **Save** |
| 🗑️ Delete | Click **Delete** on a row |

> ✅ Changes take effect **immediately** on the next transcription — no restart needed.
> 🔗 To only print the link without opening a browser: `octoasr mentions --no-browser`

---

## ⚙️ How It Works

After transcription, the server processes the text in two steps (see `server.py`):

```
Raw transcript:  艾特小明确认一下
                   │
                   ▼  ① "艾特" normalization  →  @
                 @小明确认一下
                   │
                   ▼  ② mention replacement   →  look up user.json
                 @Xiaoming确认一下             ✓
```

**① "艾特" normalization** — ASR often transcribes the spoken `@` (pronounced "at") as the Chinese word "艾特". The server first restores it (along with any trailing space) back to `@`:

| Transcript input | After normalization |
| :--- | :--- |
| `艾特小明` | `@小明` |
| `艾特 小明` | `@小明` |

**② mention replacement** — calls `replace()` to turn `@alias` into `@canonical_name` (assuming `user.json` maps `小明 → Xiaoming`):

| After normalization | Final result |
| :--- | :--- |
| `@小明` | `@Xiaoming` |

### Matching rules

- 🎯 Only replaces mentions starting with `@`; same-named text **without** `@` is left untouched.
- ↔️ The name after `@` needs a natural boundary (space, punctuation, or CN/EN switch). `@维杰 确认` replaces correctly; if it's immediately followed by more Chinese and the whole thing isn't in the map, matching may fail.
- 🔤 Supports stripping a parenthesized suffix before matching: `@达·芬奇(davinci)` → strips `(davinci)` first, then looks up.
- 🛟 If an alias is not found in the map, it is **kept as-is** without error.

---

## 📝 Editing Config Manually

> Advanced usage. If you prefer editing files directly, configs live in `~/.octoasr/mentions/`.

### user.json — recommended, simple key-value

An array where each item has `nickname` and `canonical_name`:

```json
[
  { "nickname": "小明", "canonical_name": "Xiaoming" },
  { "nickname": "小红", "canonical_name": "Xiaohong" }
]
```

### openclaw.json — structured, multiple aliases per name

Best when one person has several aliases. Both `aliases` and `uncertain_aliases` are collected:

```json
{
  "persons": {
    "p1": {
      "canonical_name": "Xiaoming",
      "aliases": [
        { "alias": "小明" },
        { "alias": "明儿" }
      ],
      "uncertain_aliases": [
        { "alias": "晓明" }
      ]
    }
  }
}
```

> ✅ No restart needed after editing: `replace()` re-reads on every transcription, so saving takes effect immediately.
> 🛡️ If the JSON is malformed, that file is skipped (other sources still used) and the main transcription flow is **not affected**.

---

## 🧩 Developer API

### Python functions · `utils/mention.py`

| Function | Purpose |
| :--- | :--- |
| `replace(text) -> str` | Replace all `@mentions` in the text, return the new text |
| `extract(text) -> list` | Extract all `@mentions` from the text (no replacement) |
| `list_user_mentions() -> list` | Read all entries from user.json |
| `add_user_mention(nickname, canonical_name) -> list` | Add/update (updates if nickname exists), returns the full list |
| `update_user_mention(index, nickname, canonical_name) -> list` | Update by index |
| `delete_user_mention(index) -> list` | Delete by index |

```python
from utils import mention

mention.add_user_mention("小明", "Xiaoming")
print(mention.list_user_mentions())   # [{'nickname': '小明', 'canonical_name': 'Xiaoming'}]
print(mention.replace("hi @小明"))     # hi @Xiaoming
```

> ⚠️ Empty `nickname` / `canonical_name` raises `ValueError`; an out-of-range index raises `IndexError`.

### HTTP API · integrated in the 8787 service

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/mentions` | Management page |
| `GET` | `/v1/mentions` | List all entries |
| `POST` | `/v1/mentions` | Add/update, body `{nickname, canonical_name}` |
| `PUT` | `/v1/mentions/{index}` | Update by index |
| `DELETE` | `/v1/mentions/{index}` | Delete by index |

```bash
# List all
curl http://127.0.0.1:8787/v1/mentions

# Add one
curl -X POST http://127.0.0.1:8787/v1/mentions \
  -H "Content-Type: application/json" \
  -d '{"nickname":"小明","canonical_name":"Xiaoming"}'
```

> Unified response format `{"ok": true, "items": [...]}`; on error, returns the corresponding 4xx / 5xx with an error message.

---

## ❓ FAQ

<details>
<summary><b>The directory <code>~/.octoasr/mentions</code> doesn't exist?</b></summary>

That's normal. It's created automatically as an empty template on the first transcription or first visit to the management page — no manual setup needed.
</details>

<details>
<summary><b>I edited it on the page but transcription didn't change?</b></summary>

Make sure the service is running and that transcription goes through the same service on the same machine. Replacement is read on the fly, so a restart is usually unnecessary; if it still misbehaves, try `octoasr restart`.
</details>

<details>
<summary><b>Speech said "艾特 someone" but it wasn't replaced with <code>@</code>?</b></summary>

Normalization only handles the literal word "艾特". Confirm the transcript actually contains "艾特", and that the nickname has a corresponding canonical name configured in user.json / the page.
</details>

<details>
<summary><b>Will it mistakenly catch the spoken phrase "艾特一下" (give a shout)?</b></summary>

Yes. Currently "艾特" is unconditionally normalized to `@`, so "艾特一下" becomes "@一下". If that alias has no mapping, the later mention replacement leaves it alone, but the `@` symbol remains.
</details>
