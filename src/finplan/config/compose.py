"""Base + overlay composition.

Semantics (the contract the whole scenario system rests on):
- mappings deep-merge key-wise; scalars and non-id lists replace wholesale
- lists whose elements are all mappings carrying an identity key ("id", or "name" for
  people) merge element-wise by that key: same key -> deep-merge, new key -> append,
  {"<identity>": ..., "remove": true} -> delete the element
"""

from __future__ import annotations

import copy
from typing import Any

_IDENTITY_KEYS = ("id", "name")


def _identity_key(items: list) -> str | None:
    for key in _IDENTITY_KEYS:
        if all(isinstance(x, dict) and key in x for x in items) and items:
            return key
    return None


def _merge_id_lists(base: list, overlay: list, key: str) -> list:
    result: list[dict] = [copy.deepcopy(x) for x in base]
    index = {x[key]: i for i, x in enumerate(result)}
    for item in overlay:
        ident = item[key]
        if item.get("remove") is True:
            if ident in index:
                removed_at = index.pop(ident)
                result = [x for x in result if x[key] != ident]
                index = {x[key]: i for i, x in enumerate(result)}
            continue
        if ident in index:
            result[index[ident]] = deep_merge(result[index[ident]], item)
        else:
            result.append(copy.deepcopy(item))
            index[ident] = len(result) - 1
    return result


def deep_merge(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = {k: copy.deepcopy(v) for k, v in base.items()}
        for k, v in overlay.items():
            merged[k] = deep_merge(base[k], v) if k in base else copy.deepcopy(v)
        return merged
    if isinstance(base, list) and isinstance(overlay, list):
        key = _identity_key(base) or _identity_key(overlay)
        if key is not None and all(isinstance(x, dict) and key in x for x in base + overlay):
            return _merge_id_lists(base, overlay, key)
        return copy.deepcopy(overlay)
    return copy.deepcopy(overlay)


def compose(base: dict, *overlays: dict) -> dict:
    """Left-to-right merge of overlay dicts onto a base dict."""
    resolved = copy.deepcopy(base)
    for ov in overlays:
        resolved = deep_merge(resolved, ov)
    return resolved
