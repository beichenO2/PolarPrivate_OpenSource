"""Expand PolarPrivate ``pp_files`` into ``<<PP_FILE>>`` blocks on the last user message.

Callers put absolute paths in the JSON body. This module reads UTF-8 text from
disk, appends tagged blocks, and strips ``pp_files`` so upstream OpenAI-compatible
APIs never see the extra field. Relative paths, missing files, and oversize
payloads fail closed. Binary files and remote URLs are out of scope.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

_DEFAULT_MAX_FILE_BYTES = 8 * 1024 * 1024
_DEFAULT_MAX_TOTAL_BYTES = 32 * 1024 * 1024
_DEFAULT_MAX_COUNT = 32


class FileInjectError(Exception):
    """Caller-facing ``pp_files`` failure. ``status_code`` maps to HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _format_block(path_label: str, data: bytes, text: str) -> str:
    digest = hashlib.sha256(data).hexdigest()[:12]
    body = text if text.endswith("\n") or text == "" else text + "\n"
    return (
        f'<<PP_FILE id="{digest}" path="{path_label}" encoding="utf-8" bytes="{len(data)}">>\n'
        f"{body}"
        f'<</PP_FILE id="{digest}">>'
    )


def _load_entry(item: Any, max_file_bytes: int) -> tuple[str, bytes, str]:
    if not isinstance(item, dict):
        raise FileInjectError("PP_FILE_ENTRY_INVALID", "each pp_files item must be an object", 422)

    if "content" in item:
        text = item["content"]
        if not isinstance(text, str):
            raise FileInjectError("PP_FILE_ENTRY_INVALID", "inline content must be a string", 422)
        data = text.encode("utf-8")
        if len(data) > max_file_bytes:
            raise FileInjectError("PP_FILE_TOO_LARGE", "pp_files inline content exceeds max bytes", 413)
        label = item.get("name") or "inline"
        if not isinstance(label, str) or not label:
            label = "inline"
        return label, data, text

    if "path" not in item:
        raise FileInjectError("PP_FILE_ENTRY_INVALID", "pp_files item needs path or content", 422)

    raw_path = item["path"]
    if not isinstance(raw_path, str) or not raw_path:
        raise FileInjectError("PP_FILE_PATH_NOT_ABSOLUTE", "pp_files path must be an absolute string", 422)

    path = Path(raw_path)
    if not path.is_absolute():
        raise FileInjectError("PP_FILE_PATH_NOT_ABSOLUTE", "pp_files path must be absolute", 422)

    try:
        st = path.stat()
    except FileNotFoundError as exc:
        raise FileInjectError("PP_FILE_NOT_FOUND", f"pp_files path not found: {path}", 422) from exc
    except OSError as exc:
        raise FileInjectError("PP_FILE_NOT_READABLE", f"pp_files path not readable: {path}", 422) from exc

    if st.st_size > max_file_bytes:
        raise FileInjectError("PP_FILE_TOO_LARGE", f"pp_files file exceeds max bytes: {path}", 413)

    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise FileInjectError("PP_FILE_NOT_FOUND", f"pp_files path not found: {path}", 422) from exc
    except IsADirectoryError as exc:
        raise FileInjectError("PP_FILE_NOT_READABLE", f"pp_files path is a directory: {path}", 422) from exc
    except OSError as exc:
        raise FileInjectError("PP_FILE_NOT_READABLE", f"pp_files path not readable: {path}", 422) from exc

    if len(data) > max_file_bytes:
        raise FileInjectError("PP_FILE_TOO_LARGE", f"pp_files file exceeds max bytes: {path}", 413)

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FileInjectError("PP_FILE_NOT_UTF8", f"pp_files path is not utf-8 text: {path}", 422) from exc

    return str(path), data, text


def _append_blocks(content: Any, blocks: str) -> Any:
    if content is None:
        return blocks
    if isinstance(content, str):
        if content == "" or content.endswith("\n"):
            return content + blocks
        return content + "\n" + blocks
    if isinstance(content, list):
        return list(content) + [{"type": "text", "text": blocks}]
    raise FileInjectError("PP_FILE_CONTENT_TYPE", "user message content must be a string or list", 422)


def expand_pp_files(obj: dict[str, Any]) -> dict[str, Any]:
    """Read ``pp_files``, append ``<<PP_FILE>>`` blocks, strip the field.

    No-op when ``pp_files`` is absent. Mutates ``obj`` and returns it.
    """
    if "pp_files" not in obj:
        return obj

    items = obj["pp_files"]
    if not isinstance(items, list):
        raise FileInjectError("PP_FILES_TYPE", "pp_files must be a list", 422)

    max_file = _int_env("PRIVPORTAL_PP_FILE_MAX_BYTES", _DEFAULT_MAX_FILE_BYTES)
    max_total = _int_env("PRIVPORTAL_PP_FILES_MAX_TOTAL_BYTES", _DEFAULT_MAX_TOTAL_BYTES)
    max_count = _int_env("PRIVPORTAL_PP_FILES_MAX_COUNT", _DEFAULT_MAX_COUNT)

    if len(items) > max_count:
        raise FileInjectError("PP_FILES_TOO_MANY", "pp_files exceeds max entry count", 422)

    loaded: list[tuple[str, bytes, str]] = []
    total = 0
    for item in items:
        label, data, text = _load_entry(item, max_file)
        total += len(data)
        if total > max_total:
            raise FileInjectError("PP_FILE_TOO_LARGE", "pp_files total size exceeds max bytes", 413)
        loaded.append((label, data, text))

    del obj["pp_files"]

    if not loaded:
        return obj

    messages = obj.get("messages")
    if not isinstance(messages, list) or not messages:
        raise FileInjectError("PP_FILE_NO_USER_MESSAGE", "pp_files requires a user message", 422)

    last_user = None
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            last_user = msg
            break
    if last_user is None:
        raise FileInjectError("PP_FILE_NO_USER_MESSAGE", "pp_files requires a user message", 422)

    blocks = "\n".join(_format_block(label, data, text) for label, data, text in loaded)
    last_user["content"] = _append_blocks(last_user.get("content"), blocks)
    return obj
