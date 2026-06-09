# coding=utf-8

import os
import re
import json

MENTION_OPENCLAW = '~/.mano-asr/mentions/openclaw.json'
MENTION_USER = '~/.mano-asr/mentions/user.json'
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
    mention_map = dict(MENTION_MAP)
    _load_openclaw_mentions(mention_map)
    _load_user_mentions(mention_map)
    return mention_map


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


def replace(text):
    if not isinstance(text, str):
        raise TypeError(f"replace expected str, got {type(text).__name__}")
    mention_map = _load_mention_map()

    def _replace_match(match):
        item = match.group(0)
        replacement = _resolve_name(item[1:], mention_map)
        if replacement:
            return f"@{replacement}"
        return item

    return MENTION_PATTERN.sub(_replace_match, text)
