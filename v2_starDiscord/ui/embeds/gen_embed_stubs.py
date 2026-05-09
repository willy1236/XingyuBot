#!/usr/bin/env python3
# tools/gen_embed_stubs.py ───────────────────────────────────────────────────
#
# 掃描 v2_starDiscord/ui/embeds/ 底下所有 .py，
# 找出 BaseTransformer[Model, Ctx] 的子類別，
# 自動生成 v2_starDiscord/ui/embeds/__init__.pyi。
#
# 使用方式：
#   python tools/gen_embed_stubs.py
#
# 建議加入 Makefile：
#   gen-stubs:
#       python tools/gen_embed_stubs.py
# ────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

# ── 設定 ─────────────────────────────────────────────────────────────────────

EMBEDS_DIR = Path("v2_starDiscord/ui/embeds")
OUTPUT_PYI = Path("v2_starDiscord/ui/embeds/__init__.pyi")
BASE_CLASS = "BaseTransformer"
PACKAGE_PREFIX = "v2_starDiscord.ui."  # EMBEDS_DIR 對應的 Python package 前綴

# ── 資料結構 ─────────────────────────────────────────────────────────────────


@dataclass
class TransformerEntry:
    model_type: str  # e.g. "UserModerate"
    ctx_type: str  # e.g. "UserModerateCtx"
    source_file: Path  # 定義該 Transformer 的 .py 路徑


# ── AST 掃描：Transformer 收集 ────────────────────────────────────────────────


def extract_entries(path: Path) -> list[TransformerEntry]:
    """從單一 .py 找出所有 BaseTransformer[Model, Ctx] 子類別。"""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"  [skip] {path}: SyntaxError – {e}", file=sys.stderr)
        return []

    entries: list[TransformerEntry] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            if not isinstance(base, ast.Subscript):
                continue
            if not (isinstance(base.value, ast.Name) and base.value.id == BASE_CLASS):
                continue
            slc = base.slice
            if not isinstance(slc, ast.Tuple) or len(slc.elts) != 2:
                continue
            entries.append(
                TransformerEntry(
                    model_type=ast.unparse(slc.elts[0]),
                    ctx_type=ast.unparse(slc.elts[1]),
                    source_file=path,
                )
            )
    return entries


def collect_all_entries() -> list[TransformerEntry]:
    all_entries: list[TransformerEntry] = []
    for path in sorted(EMBEDS_DIR.rglob("*.py")):
        if path.name.startswith("_"):
            continue
        found = extract_entries(path)
        if found:
            print(f"  found {len(found)} transformer(s) in {path}")
        all_entries.extend(found)
    return all_entries


# ── 來源查找 ──────────────────────────────────────────────────────────────────


def collect_import_origins(source_file: Path) -> dict[str, str]:
    """
    從 .py 的 import 語句建立 {local_name: module} 對照表。
    用於反查 model_type 是從哪個套件 import 進來的。

    e.g. `from v2_starlib.database.postgresql.models import UserModerate`
         → {"UserModerate": "v2_starlib.database.postgresql.models"}
    """
    source = source_file.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    origins: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if not node.module or node.level:  # 跳過 relative import
            continue
        for alias in node.names:
            local_name = alias.asname or alias.name
            origins[local_name] = node.module
    return origins


def file_to_module(path: Path, relative_to: Path, prefix: str) -> str:
    """把檔案路徑轉成 Python module 字串。"""
    parts = list(path.relative_to(relative_to).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return prefix + ".".join(parts)


def find_class_module(name: str, search_dir: Path, prefix: str) -> str | None:
    """
    在 search_dir 底下找 class 名稱為 name 的定義，
    回傳對應的 module 字串。找不到回傳 None。
    """
    for path in sorted(search_dir.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == name:
                return file_to_module(path, search_dir.parent, prefix)
    return None


# ── .pyi 生成 ────────────────────────────────────────────────────────────────

HEADER = """\
# __init__.pyi ────────────────────────────────────────────────────────────────
# 此檔案由 tools/gen_embed_stubs.py 自動生成，請勿手動編輯。
# 重新生成：python tools/gen_embed_stubs.py
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

from typing import overload

import discord

from v2_starDiscord.ui.embeds.base import EmptyContext as EmptyContext
from v2_starDiscord.ui.embeds.base import EmbedFactory as EmbedFactory
"""


def build_pyi(entries: list[TransformerEntry], package_prefix: str) -> str:
    seen_names: set[str] = set()
    reexport_lines: list[str] = []

    for entry in entries:
        # model：定義在第三方套件，從來源檔的 import 語句反查來源 module
        # ctx  ：定義在 embeds/ 內部，直接掃 class 定義位置
        import_origins = collect_import_origins(entry.source_file)

        for name, use_import_origin in [
            (entry.model_type, True),
            (entry.ctx_type, False),
        ]:
            if name in seen_names or name == "EmptyContext":
                continue
            seen_names.add(name)

            if use_import_origin:
                # model：從 import 語句反查
                module = import_origins.get(name)
                if not module:
                    print(
                        f"  [warn] {name} 在 {entry.source_file} 找不到 import 來源，跳過",
                        file=sys.stderr,
                    )
                    continue
            else:
                # ctx：掃 class 定義位置（先找同檔目錄，再往整個 EMBEDS_DIR）
                module = find_class_module(name, entry.source_file.parent, package_prefix)
                if not module:
                    module = find_class_module(name, EMBEDS_DIR, package_prefix)
                if not module:
                    print(
                        f"  [warn] {name} 找不到 class 定義位置，跳過",
                        file=sys.stderr,
                    )
                    continue

            reexport_lines.append(f"from {module} import {name} as {name}")

    model_types = sorted({e.model_type for e in entries})
    ctx_types = sorted({e.ctx_type for e in entries})

    # 每個 model 生成四個 overload：
    #   to_embed  × (single | list) → discord.Embed
    #   to_embeds × (single | list) → list[discord.Embed]
    overload_blocks: list[str] = []
    for entry in entries:
        M, C = entry.model_type, entry.ctx_type
        overload_blocks.append(
            f"    # ── {M} ──\n"
            f"    @classmethod\n"
            f"    @overload\n"
            f"    def to_embed(cls, data: {M}, ctx: {C}) -> discord.Embed: ...\n"
            f"    @classmethod\n"
            f"    @overload\n"
            f"    def to_embed(cls, data: list[{M}], ctx: {C}) -> discord.Embed: ...\n"
            f"    @classmethod\n"
            f"    @overload\n"
            f"    def to_embeds(cls, data: {M}, ctx: {C}) -> list[discord.Embed]: ...\n"
            f"    @classmethod\n"
            f"    @overload\n"
            f"    def to_embeds(cls, data: list[{M}], ctx: {C}) -> list[discord.Embed]: ..."
        )

    # fallback
    overload_blocks.append(
        "    # ── fallback ──\n"
        "    @classmethod\n"
        "    @overload\n"
        "    def to_embed(cls, data: object, ctx: EmptyContext = ...) -> discord.Embed: ...\n"
        "    @classmethod\n"
        "    @overload\n"
        "    def to_embeds(cls, data: object, ctx: EmptyContext = ...) -> list[discord.Embed]: ..."
    )

    factory_body = "\n\n".join(overload_blocks)

    return (
        HEADER
        + ("\n".join(reexport_lines) + "\n\n" if reexport_lines else "\n")
        + f"# 已收錄模型：{', '.join(model_types)}\n"
        + f"# 已收錄 Context：{', '.join(ctx_types)}\n"
        + "\n\n"
        + "class EmbedFactory:\n"
        + factory_body
        + "\n\n\n"
    )


# ── 主程式 ───────────────────────────────────────────────────────────────────


def main() -> None:
    print(f"掃描 {EMBEDS_DIR} ...")

    if not EMBEDS_DIR.exists():
        print(f"[error] 找不到目錄：{EMBEDS_DIR}", file=sys.stderr)
        sys.exit(1)

    entries = collect_all_entries()

    if not entries:
        print("[warn] 沒有找到任何 BaseTransformer 子類別，.pyi 不會更新。")
        return

    print(f"\n共找到 {len(entries)} 個 transformer：")
    for e in entries:
        print(f"  {e.model_type:30s} → ctx: {e.ctx_type}")

    pyi_content = build_pyi(entries, PACKAGE_PREFIX)
    OUTPUT_PYI.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PYI.write_text(pyi_content, encoding="utf-8")
    print(f"\n已生成：{OUTPUT_PYI}")


if __name__ == "__main__":
    main()
