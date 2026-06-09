# coding=utf-8

import os
import re
import json

MENTION_DIR = '~/.mano-asr/mentions'
MENTION_OPENCLAW = '~/.mano-asr/mentions/openclaw.json'
MENTION_USER = '~/.mano-asr/mentions/user.json'

# Valid empty templates written when files are missing, so later loading
# never fails due to malformed format.
MENTION_DEFAULTS = {
    MENTION_OPENCLAW: {"persons": {}},
    MENTION_USER: [],
}
MENTION_PATTERN = re.compile(
    r"@[A-Za-z0-9_\u4e00-\u9fff丨·]+"
    r"(?:[（(][A-Za-z0-9_丨·]+[）)])?"
)
PAREN_SUFFIX_PATTERN = re.compile(r"[（(][A-Za-z0-9_丨·]+[）)]$")

MENTION_MAP = {
    "毕达哥拉斯": "pythagoras",
    "彭特兰": "pentland",
    "布鲁克斯": "Brooks",
    "哥德尔": "godel",
    "冯·诺伊曼": "vonneumann",
    "冯诺伊曼": "vonneumann",
    "达芬奇": "DaVinci",
    "达·芬奇": "DaVinci",
    "卡诺": "Kano",
    "Guiguzi": "鬼谷子",
    "Socrates": "苏格拉底",
    "Sokrates": "苏格拉底",
    "科特": "Kotter",
}


def _ensure_mention_files():
    """Ensure the mentions directory and config files exist, creating empty
    templates if missing.

    Failures (e.g. insufficient permissions) are not raised; callers fall back
    to using only the built-in MENTION_MAP.
    """
    try:
        os.makedirs(os.path.expanduser(MENTION_DIR), exist_ok=True)
        for path, default in MENTION_DEFAULTS.items():
            expanded_path = os.path.expanduser(path)
            if not os.path.exists(expanded_path):
                with open(expanded_path, 'w', encoding='utf-8') as f:
                    json.dump(default, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _load_json_file(path):
    expanded_path = os.path.expanduser(path)
    if not os.path.exists(expanded_path):
        return None

    with open(expanded_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _load_openclaw_mentions(mention_map):
    mention_openclaw = _load_json_file(MENTION_OPENCLAW)
    if not isinstance(mention_openclaw, dict):
        return

    persons = mention_openclaw.get("persons", {})
    if not isinstance(persons, dict):
        raise ValueError(f"Invalid mention config field: {MENTION_OPENCLAW} persons must be an object")

    for _, person in persons.items():
        if not isinstance(person, dict):
            continue

        canonical_name = person.get('canonical_name')
        aliases = person.get('aliases', []) + person.get('uncertain_aliases', [])
        if not canonical_name or not isinstance(aliases, list):
            continue

        for alias_item in aliases:
            if not isinstance(alias_item, dict):
                continue

            alias = alias_item.get('alias')
            if alias:
                mention_map[alias] = canonical_name


def _load_user_mentions(mention_map):
    mention_user = _load_json_file(MENTION_USER)
    if mention_user is None:
        return
    if not isinstance(mention_user, list):
        raise ValueError(f"Invalid mention config: {MENTION_USER} must be a list")

    for item in mention_user:
        if not isinstance(item, dict):
            continue

        nickname = item.get("nickname")
        canonical_name = item.get("canonical_name")
        if nickname and canonical_name:
            mention_map[nickname] = canonical_name


def _load_mention_map():
    _ensure_mention_files()
    mention_map = dict(MENTION_MAP)
    _load_openclaw_mentions(mention_map)
    _load_user_mentions(mention_map)
    return mention_map


# ---------------------------------------------------------------------------
# CRUD for user.json (used by the visual management page)
# Entry format: {"nickname": "...", "canonical_name": "..."}
# Write format is strictly aligned with _load_user_mentions read logic;
# changes take effect on the next transcription immediately.
# ---------------------------------------------------------------------------

def _save_user_mentions(items):
    _ensure_mention_files()
    expanded_path = os.path.expanduser(MENTION_USER)
    with open(expanded_path, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def list_user_mentions():
    """Return all entries in user.json; returns an empty list if missing or unparseable."""
    _ensure_mention_files()
    data = _load_json_file(MENTION_USER)
    if not isinstance(data, list):
        return []

    items = []
    for item in data:
        if not isinstance(item, dict):
            continue
        nickname = item.get("nickname")
        canonical_name = item.get("canonical_name")
        if nickname and canonical_name:
            items.append({"nickname": nickname, "canonical_name": canonical_name})
    return items


def _validate_pair(nickname, canonical_name):
    if not isinstance(nickname, str) or not isinstance(canonical_name, str):
        raise ValueError("nickname and canonical_name must be strings")
    nickname = nickname.strip()
    canonical_name = canonical_name.strip()
    if not nickname or not canonical_name:
        raise ValueError("nickname and canonical_name must not be empty")
    return nickname, canonical_name


def add_user_mention(nickname, canonical_name):
    """Add an entry; if nickname already exists, update its canonical_name. Returns the full list."""
    nickname, canonical_name = _validate_pair(nickname, canonical_name)
    items = list_user_mentions()

    for item in items:
        if item["nickname"] == nickname:
            item["canonical_name"] = canonical_name
            break
    else:
        items.append({"nickname": nickname, "canonical_name": canonical_name})

    _save_user_mentions(items)
    return items


def update_user_mention(index, nickname, canonical_name):
    """Update the entry at the given index. Raises IndexError if out of range. Returns the full list."""
    nickname, canonical_name = _validate_pair(nickname, canonical_name)
    items = list_user_mentions()
    if index < 0 or index >= len(items):
        raise IndexError(f"mention index out of range: {index}")

    items[index] = {"nickname": nickname, "canonical_name": canonical_name}
    _save_user_mentions(items)
    return items


def delete_user_mention(index):
    """Delete the entry at the given index. Raises IndexError if out of range. Returns the full list."""
    items = list_user_mentions()
    if index < 0 or index >= len(items):
        raise IndexError(f"mention index out of range: {index}")

    items.pop(index)
    _save_user_mentions(items)
    return items


def extract(text):
    if not isinstance(text, str):
        raise TypeError(f"extract expected str, got {type(text).__name__}")
    return MENTION_PATTERN.findall(text)


def _resolve_name(name, mention_map):
    if name in mention_map:
        return mention_map[name]

    base_name = PAREN_SUFFIX_PATTERN.sub("", name)
    if base_name != name and base_name in mention_map:
        return mention_map[base_name]
    return None


def _resolve_candidate(candidate_name, mention_map):
    """Reverse-decreasing match over a candidate name.
    """
    for end in range(len(candidate_name), 0, -1):
        alias = candidate_name[:end]
        canonical_name = _resolve_name(alias, mention_map)
        if canonical_name:
            return alias, canonical_name, candidate_name[end:]
    return None, None, candidate_name


def replace(text):
    if not isinstance(text, str):
        raise TypeError(f"replace expected str, got {type(text).__name__}")
    mention_map = _load_mention_map()

    def _replace_match(match):
        item = match.group(0)
        _, canonical_name, rest = _resolve_candidate(item[1:], mention_map)
        if not canonical_name:
            return item
        if rest:
            # Mention was stuck to following text; reinsert a separating space.
            return f"@{canonical_name} {rest}"
        return f"@{canonical_name}"

    return MENTION_PATTERN.sub(_replace_match, text)
