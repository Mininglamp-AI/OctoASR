# coding=utf-8
"""Semantic @mention judge.

Given one ASR transcript line plus group-chat context, decide whether an
``@someone`` prefix should be added and, if so, who. The judgement is produced
by an independent local model loaded via ``mlx_vlm`` (a Qwen3.5 Omni/VLM).

This module is intentionally separate from ``utils.mention``:
  - ``utils.mention``  -> dictionary/regex replacement of *existing* @nicknames
  - ``core.mention``   -> semantic judgement of *whether to add* an @

The model only outputs ``targets``; the actual ``@name `` prefixing is done in
Python (``apply_mention``). The system prompt is read from a file so it can be
swapped by developers without touching code.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("server")

# ---------------------------------------------------------------------------
# System prompt loading (file-based, developer-editable, no CLI override)
# ---------------------------------------------------------------------------

# core/mention.py lives in <root>/core/, prompt lives in <root>/docs/.
# After a brew install, `core/` is copied into site-packages and the prompt is
# copied to site-packages/docs/ (see homebrew/octoasr.rb & build-bottle.sh),
# so parent.parent/docs still resolves. A secondary candidate under
# core/prompts/ is kept as a fallback.
_PROMPT_CANDIDATES = [
    Path(__file__).resolve().parent.parent / "docs" / "prompt.txt",
    Path(__file__).resolve().parent / "prompts" / "prompt.txt",
]

DEFAULT_PROMPT_PATH = _PROMPT_CANDIDATES[0]


def load_prompt(path: Optional[str] = None) -> str:
    """Read the system prompt from disk.

    If ``path`` is given it is used directly; otherwise the first existing
    candidate is used. Raises FileNotFoundError with a clear message when none
    is found (caught by MentionJudge.from_pretrained -> cooldown).
    """
    if path is not None:
        p = Path(path).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"mention prompt file not found: {p}")
        return p.read_text(encoding="utf-8")

    for candidate in _PROMPT_CANDIDATES:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")

    raise FileNotFoundError(
        "mention prompt file not found in any candidate location: "
        + ", ".join(str(c) for c in _PROMPT_CANDIDATES)
    )


# ---------------------------------------------------------------------------
# Pure helpers (no model needed)
# ---------------------------------------------------------------------------

def is_group_chat(chat_context: Optional[str]) -> bool:
    """Return True only when chat_context starts with 「群聊」.

    Private chats ("私聊..."), empty, or any other prefix -> False. Upstream
    guarantees chat_context begins with either "群聊" or "私聊".
    """
    return (chat_context or "").strip().startswith("群聊")


def build_user_content(
    asr_text: str,
    chat_context: str = "",
    member_context: str = "",
) -> str:
    """Assemble the user message fed to the judge model (matches eval script)."""
    return "\n".join([
        "asr_text: " + str(asr_text),
        "chat_context: " + str(chat_context),
        "member_context: " + str(member_context),
    ])


def parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Three-tier tolerant JSON parse (matches eval script).

    1. strip ```json fences and json.loads
    2. json.loads directly
    3. regex-grab the first {...} block
    Returns None on total failure.
    """
    text = (text or "").strip()
    stripped = re.sub(r"^```(?:json)?\s*", "", text)
    stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def empty_result(skipped: Optional[str] = None) -> Dict[str, Any]:
    """Uniform empty judgement, so the `mention` field shape stays consistent."""
    result: Dict[str, Any] = {
        "is_imperative": False,
        "should_mention": False,
        "targets": [],
        "confidence": 0.0,
    }
    if skipped:
        result["skipped"] = skipped
    return result


# ---------------------------------------------------------------------------
# The judge model
# ---------------------------------------------------------------------------

class MentionJudge:
    """Wraps an mlx_vlm model that outputs the @mention judgement as JSON."""

    def __init__(self, model, processor, config, system_prompt: str):
        self.model = model
        self.processor = processor
        self.config = config
        self.system_prompt = system_prompt

    @classmethod
    def from_pretrained(cls, model_path: str) -> "MentionJudge":
        # Lazy import: environments without mlx_vlm can still `import server`.
        from mlx_vlm import load
        from mlx_vlm.utils import load_config

        system_prompt = load_prompt()
        model, processor = load(model_path)
        try:
            import cider
        except ImportError:
            cider = None
        if cider is not None and cider.is_available():
            import mlx.core as mx
            stats = cider.convert_model(model.language_model)
            mx.eval(model.parameters())
            logger.info(f"[mention] cider status: {stats}")
            
        config = load_config(model_path)
        return cls(model, processor, config, system_prompt)

    def judge(
        self,
        asr_text: str,
        chat_context: str = "",
        member_context: str = "",
        *,
        max_tokens: int = 512,
    ) -> Dict[str, Any]:
        """Run inference only (group/private short-circuit is done in server).

        Returns a parsed judgement dict. On parse failure logs a WARNING with
        the raw model output (truncated) and returns an empty result. Inference
        exceptions propagate to the caller (server logs ERROR + degrades).
        """
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": build_user_content(
                asr_text, chat_context, member_context)},
        ]
        formatted = apply_chat_template(
            self.processor, self.config, messages, num_images=0)
        out = generate(
            self.model, self.processor, formatted,
            max_tokens=max_tokens, verbose=False)
        resp = out if isinstance(out, str) else getattr(out, "text", str(out))

        parsed = parse_json(resp)
        if parsed is None:
            logger.warning("[mention] JSON parse failed, raw=%s", (resp or "")[:200])
            return empty_result()
        return parsed


# ---------------------------------------------------------------------------
# Prefixing (model only outputs targets; we build the @name text here)
# ---------------------------------------------------------------------------

def apply_mention(asr_text: str, mention_result: Optional[Dict[str, Any]]) -> str:
    """Prefix `@name ` to asr_text when the judgement says so.

    - empty / should_mention not True / no targets -> asr_text unchanged
    - asr_text already starts with '@' -> unchanged (double safety)
    - otherwise: '@A @B ' + asr_text (one space before the body; malformed
      targets are skipped, not fatal)
    """
    if not mention_result or not mention_result.get("should_mention"):
        return asr_text

    targets = mention_result.get("targets") or []
    if not targets:
        return asr_text

    if asr_text.lstrip().startswith("@"):
        return asr_text

    names: List[str] = []
    for t in targets:
        if not isinstance(t, dict):
            logger.warning("[mention] skip malformed target: %r", t)
            continue
        name = t.get("display_name")
        if not name:
            mention_text = t.get("mention_text") or ""
            name = mention_text.lstrip("@").strip()
        if name:
            names.append(name)
        else:
            logger.warning("[mention] skip target without name: %r", t)

    if not names:
        return asr_text

    return f"@{' @'.join(names)} {asr_text}"
