#!/usr/bin/env python3
"""Generate RecipeJson files from the current Deluxe Workshop sources.

The Deluxe Workshop files contain three independently selectable editions and
use compact ``Custom String``/``String Split`` tables.  The older TypeScript
loader only understands literal ``Array(...)`` expressions, so this generator
decodes the compact tables directly.

Usage (from the frontend repository):

    python3 scripts/generate-deluxe-recipes.py ../ow_restaurant

The command writes nine files under ``store``: one for every supported Deluxe
source language (ko/en/ja) and edition (org/cafe/gc).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FRONTEND_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = FRONTEND_ROOT / "store"

LANGUAGE_FILES = {
    "ko": "kr_deluxe.ow",
    "en": "en_deluxe.ow",
    "ja": "jp_deluxe.ow",
}

SOURCE_REPOSITORY = "https://github.com/DoubleJONY/ow_restaurant"
MANIFEST_PATH = OUTPUT_DIR / "recipe-deluxe-manifest.json"

EDITION_ITEM_COUNTS = {
    "org": 476,
    "cafe": 399,
    "gc": 464,
}

ACTION_TYPES = {
    "cut": 0,
    "grill": 1,
    "fry": 2,
    "pot": 3,
    "pan": 4,
    "impact": 5,
    "mix": 6,
    "ice": 7,
}

PER_ITEM_PHASE1 = (
    "ITEM_COLOR",
    "ITEM_NAME",
    "CUTTING_NEEDED",
    "CUTTING_RESULT",
    "GRILLING_NEEDED",
    "GRILLING_RESULT",
    "FRYING_NEEDED",
    "FRYING_RESULT",
    "ICE_NEEDED",
    "ICE_RESULT",
)

PER_ITEM_PHASE2 = (
    "POT_TIME",
    "POT_RESULT",
    "PAN_NEEDED",
    "PAN_RESULT",
    "IMPACT_RESULT",
    "ADDITIONAL_MATERIAL_LIST",
)

STAGE_TABLES = (
    "FRIDGE_LIST",
    "MENU_LIST",
    "HAZARD_MENU_LIST",
    "WEAVER_MENU_LIST",
)


class ParseError(RuntimeError):
    """Raised when a Deluxe source no longer matches the supported format."""


@dataclass(frozen=True)
class Assignment:
    expression: str


def scan_balanced(text: str, start: int, opener: str, closer: str) -> int:
    if start >= len(text) or text[start] != opener:
        raise ParseError(f"expected {opener!r} at offset {start}")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return index + 1
    raise ParseError(f"unclosed {opener!r} at offset {start}")


def split_top_level(text: str, delimiter: str = ",") -> list[str]:
    parts: list[str] = []
    start = 0
    paren = bracket = brace = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "(":
            paren += 1
        elif char == ")":
            paren -= 1
        elif char == "[":
            bracket += 1
        elif char == "]":
            bracket -= 1
        elif char == "{":
            brace += 1
        elif char == "}":
            brace -= 1
        elif char == delimiter and paren == bracket == brace == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return parts


def unwrap_call(expression: str, expected: str | None = None) -> tuple[str, list[str], str]:
    expression = expression.strip()
    match = re.match(r"^([A-Za-z][A-Za-z 0-9]*)\s*\(", expression)
    if not match:
        raise ParseError(f"not a call: {expression[:80]!r}")
    name = match.group(1).strip()
    if expected is not None and name != expected:
        raise ParseError(f"expected {expected}, got {name}")
    open_at = expression.find("(", match.start())
    end = scan_balanced(expression, open_at, "(", ")")
    return name, split_top_level(expression[open_at + 1 : end - 1]), expression[end:].strip()


def eval_expr(expression: str) -> Any:
    expression = expression.strip()
    if not expression:
        raise ParseError("empty expression")
    if expression.startswith('"'):
        try:
            return json.loads(expression)
        except json.JSONDecodeError as exc:
            raise ParseError(f"invalid string literal: {expression[:100]!r}") from exc
    if re.fullmatch(r"-?\d+(?:\.\d+)?", expression):
        return float(expression) if "." in expression else int(expression)
    if expression in {"Null", "False", "True"}:
        return expression
    if expression == "Empty Array":
        return []

    name, args, suffix = unwrap_call(expression)
    if name == "Custom String":
        rendered = eval_expr(args[0])
        if not isinstance(rendered, str):
            raise ParseError("Custom String format is not a string")
        for index, arg in enumerate(args[1:]):
            rendered = rendered.replace("{" + str(index) + "}", str(eval_expr(arg)))
        if suffix:
            raise ParseError(f"unexpected Custom String suffix: {suffix!r}")
        return rendered
    if name == "String Split":
        source = eval_expr(args[0])
        separator = eval_expr(args[1])
        if suffix:
            raise ParseError(f"unexpected String Split suffix: {suffix!r}")
        return source.split(separator)
    if name == "Append To Array":
        result: list[Any] = []
        for arg in args:
            value = eval_expr(arg)
            result.extend(value if isinstance(value, list) else [value])
        if suffix:
            raise ParseError(f"unexpected Append To Array suffix: {suffix!r}")
        return result
    if name == "Mapped Array":
        # Deluxe's static payload is always the first argument.  The second
        # argument maps numeric/color tokens at runtime; the frontend needs the
        # token values themselves, which are normalized below.
        return eval_expr(args[0])
    if name == "Array":
        if suffix:
            raise ParseError(f"indexed Array is not a static table: {suffix!r}")
        return [eval_expr(arg) for arg in args]
    raise ParseError(f"unsupported expression call: {name!r}")


def find_rule(source: str, subroutine: str) -> str:
    event = re.search(rf"(?m)^[ \t]+{re.escape(subroutine)};\r?$", source)
    if not event:
        raise ParseError(f"subroutine event not found: {subroutine}")
    start = source.rfind('rule("', 0, event.start())
    if start < 0:
        raise ParseError(f"rule start not found: {subroutine}")
    open_at = source.find("{", start)
    return source[start : scan_balanced(source, open_at, "{", "}")]


def find_all_assignments(block: str, name: str) -> list[Assignment]:
    pattern = re.compile(rf"(?m)^[ \t]+Global\.{re.escape(name)}\s*=\s*")
    assignments: list[Assignment] = []
    for match in pattern.finditer(block):
        expr_start = match.end()
        paren = bracket = 0
        in_string = escaped = False
        for index in range(expr_start, len(block)):
            char = block[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "(":
                paren += 1
            elif char == ")":
                paren -= 1
            elif char == "[":
                bracket += 1
            elif char == "]":
                bracket -= 1
            elif char == ";" and paren == bracket == 0:
                assignments.append(Assignment(block[expr_start:index].strip()))
                break
        else:
            raise ParseError(f"unterminated assignment: {name}")
    return assignments


def find_assignment(block: str, name: str, occurrence: int = 0) -> Assignment:
    assignments = find_all_assignments(block, name)
    if len(assignments) <= occurrence:
        raise ParseError(f"assignment not found: {name}[occurrence={occurrence}]")
    return assignments[occurrence]


def find_patches(block: str, name: str) -> dict[int, Any]:
    pattern = re.compile(rf"(?m)^[ \t]+Global\.{re.escape(name)}\[(\d+)\]\s*=\s*")
    patches: dict[int, Any] = {}
    for match in pattern.finditer(block):
        expr_start = match.end()
        paren = bracket = 0
        in_string = escaped = False
        for index in range(expr_start, len(block)):
            char = block[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "(":
                paren += 1
            elif char == ")":
                paren -= 1
            elif char == "[":
                bracket += 1
            elif char == "]":
                bracket -= 1
            elif char == ";" and paren == bracket == 0:
                patches[int(match.group(1))] = eval_expr(block[expr_start:index])
                break
        else:
            raise ParseError(f"unterminated patch: {name}[{match.group(1)}]")
    return patches


def normalize_scalar(value: Any) -> Any:
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value):
        return int(value)
    if value == "False" or value == "Null":
        return 0
    if value == "True":
        return 1
    return value


def normalize_nested(value: Any) -> Any:
    if isinstance(value, list):
        return [normalize_nested(item) for item in value]
    return normalize_scalar(value)


def read_per_item_table(block: str, name: str, item_count: int) -> list[Any]:
    values = normalize_nested(eval_expr(find_assignment(block, name).expression))
    if not isinstance(values, list):
        raise ParseError(f"{name} is not an array")
    for index, value in find_patches(block, name).items():
        values[index] = normalize_nested(value)
    if len(values) != item_count:
        raise ParseError(f"{name} length {len(values)} != {item_count}")
    return values


def read_stage_table(block: str, name: str) -> list[list[int]]:
    encoded = eval_expr(find_assignment(block, name).expression)
    if not isinstance(encoded, list):
        raise ParseError(f"{name} is not an array")
    if encoded and all(isinstance(value, str) for value in encoded):
        try:
            decoded = [[int(item) for item in group.split(",")] for group in encoded]
        except ValueError as exc:
            raise ParseError(f"{name} contains a non-integer item id") from exc
    else:
        decoded = normalize_nested(encoded)
    if len(decoded) != 12 or any(not isinstance(group, list) or not group for group in decoded):
        raise ParseError(f"{name} must contain 12 non-empty stage arrays")
    return decoded


def read_raw_recipes(block: str) -> tuple[list[int], list[int]]:
    raw_mix_assignments = find_all_assignments(block, "RAW_MIX")
    raw_result_assignments = find_all_assignments(block, "RAW_RESULT")
    if len(raw_mix_assignments) < 1 or len(raw_result_assignments) != 2:
        raise ParseError("compressed RAW_MIX/RAW_RESULT assignment shape changed")
    left = normalize_nested(eval_expr(raw_mix_assignments[0].expression))
    right = normalize_nested(eval_expr(raw_result_assignments[0].expression))
    result = normalize_nested(eval_expr(raw_result_assignments[1].expression))
    if not (len(left) == len(right) == len(result)):
        raise ParseError("RAW_MIX left/right/result row counts differ")
    return [a * 1000 + b for a, b in zip(left, right)], result


def make_action(action_type: str, inputs: list[int], outputs: list[int], effort: int | None) -> dict[str, Any]:
    return {
        "type": ACTION_TYPES[action_type],
        "input": inputs,
        "output": outputs,
        "effort": effort,
    }


def build_actions(tables: dict[str, list[Any]], raw_mix: list[int], raw_result: list[int], has_ice: bool) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    item_count = len(tables["ITEM_NAME"])
    for item_id in range(item_count):
        cut_effort = tables["CUTTING_NEEDED"][item_id]
        cut_result = tables["CUTTING_RESULT"][item_id]
        if cut_effort != 99:
            outputs = cut_result if isinstance(cut_result, list) else [cut_result]
            if not outputs or any(output == 0 for output in outputs):
                raise ParseError(f"active cutting action {item_id} has no output")
            actions.append(make_action("cut", [item_id], outputs, cut_effort))

        for action_type, result_key, effort_key in (
            ("grill", "GRILLING_RESULT", "GRILLING_NEEDED"),
            ("fry", "FRYING_RESULT", "FRYING_NEEDED"),
            ("pan", "PAN_RESULT", "PAN_NEEDED"),
        ):
            result = tables[result_key][item_id]
            if result != 0:
                actions.append(make_action(action_type, [item_id], [result], tables[effort_key][item_id]))

        pot_effort = tables["POT_TIME"][item_id]
        pot_result = tables["POT_RESULT"][item_id]
        if pot_effort != 0:
            if pot_result == 0:
                raise ParseError(f"active pot action {item_id} has no output")
            actions.append(make_action("pot", [item_id], [pot_result], pot_effort))

        impact_result = tables["IMPACT_RESULT"][item_id]
        if impact_result != 0:
            actions.append(make_action("impact", [item_id], [impact_result], None))

        if has_ice:
            ice_result = tables["ICE_RESULT"][item_id]
            if ice_result != 0:
                actions.append(
                    make_action("ice", [item_id], [ice_result], tables["ICE_NEEDED"][item_id])
                )

    for packed, result in zip(raw_mix, raw_result):
        actions.append(make_action("mix", [packed % 1000, packed // 1000], [result], None))
    return actions


def validate_item_ref(value: int, item_count: int, context: str) -> None:
    if not isinstance(value, int) or not 0 <= value < item_count:
        raise ParseError(f"{context} references invalid item id {value!r}")


def validate_recipe(recipe: dict[str, Any], expected_count: int, context: str) -> None:
    items = recipe["items"]
    actions = recipe["actions"]
    stages = recipe["stages"]
    if len(items) != expected_count:
        raise ParseError(f"{context}: item count {len(items)} != {expected_count}")
    if [item["id"] for item in items] != list(range(expected_count)):
        raise ParseError(f"{context}: item ids are not contiguous")
    if len(stages) != 12:
        raise ParseError(f"{context}: stage count {len(stages)} != 12")

    for item in items:
        if len(item["name"]) != 4 or any(
            not isinstance(name, str) or not name for name in item["name"]
        ):
            raise ParseError(f"{context}: item {item['id']} has an empty name")
        if not re.fullmatch(r"[A-Z]", item["colorCode"]):
            raise ParseError(f"{context}: item {item['id']} has invalid color code")
        for ref in item["additionalItems"]:
            validate_item_ref(ref, expected_count, f"{context} item {item['id']} additionalItems")
    for action_index, action in enumerate(actions):
        if action["type"] not in ACTION_TYPES.values() or not action["input"] or not action["output"]:
            raise ParseError(f"{context}: action {action_index} has an invalid shape")
        if action["type"] in (ACTION_TYPES["impact"], ACTION_TYPES["mix"]):
            if action["effort"] is not None:
                raise ParseError(f"{context}: effortless action {action_index} has effort")
        elif not isinstance(action["effort"], int):
            raise ParseError(f"{context}: action {action_index} has invalid effort")
        for ref in action["input"] + action["output"]:
            validate_item_ref(ref, expected_count, f"{context} action {action_index}")
    if [stage["id"] for stage in stages] != list(range(12)):
        raise ParseError(f"{context}: stage ids are not contiguous")
    for stage in stages:
        if len(stage["name"]) != 4 or any(not name for name in stage["name"]):
            raise ParseError(f"{context}: stage {stage['id']} has an empty name")
        for field in ("fridge", "menus", "hazardMenus", "weaverMenus"):
            for ref in stage[field]:
                validate_item_ref(ref, expected_count, f"{context} stage {stage['id']} {field}")


def parse_edition(source: str, language: str, edition: str) -> dict[str, Any]:
    item_count = EDITION_ITEM_COUNTS[edition]
    phase1 = find_rule(source, f"dataInit_{edition}1")
    phase2 = find_rule(source, f"dataInit_{edition}2")

    tables: dict[str, list[Any]] = {}
    for name in PER_ITEM_PHASE1:
        if name.startswith("ICE_") and edition != "cafe":
            continue
        tables[name] = read_per_item_table(phase1, name, item_count)
    for name in PER_ITEM_PHASE2:
        tables[name] = read_per_item_table(phase2, name, item_count)

    raw_mix, raw_result = read_raw_recipes(phase2)
    stage_tables = {name: read_stage_table(phase2, name) for name in STAGE_TABLES}
    stage_names = eval_expr(find_assignment(phase2, "STAGE_NAME").expression)
    if not isinstance(stage_names, list) or len(stage_names) != 12:
        raise ParseError(f"{language}/{edition}: STAGE_NAME must contain 12 names")

    melt_ids: set[int] = set()
    if edition == "org":
        # Deluxe reuses ICE_RESULT as storage for the original edition's
        # MELT_LIST after the cafe-only ice tables are no longer live.
        melt_ids = set(normalize_nested(eval_expr(find_assignment(phase2, "ICE_RESULT").expression)))

    items = []
    for item_id, name in enumerate(tables["ITEM_NAME"]):
        additional = tables["ADDITIONAL_MATERIAL_LIST"][item_id]
        if additional == 0:
            additional_items: list[int] = []
        elif isinstance(additional, list):
            additional_items = additional
        else:
            additional_items = [additional]
        items.append(
            {
                "id": item_id,
                # Each JSON is locale-specific because the stage/menu logic can
                # differ by locale.  Repeating the native source string keeps
                # RecipeJson's established four-name schema without coupling
                # it to another locale's stage ordering.
                "name": [name, name, name, name],
                "canMelt": item_id in melt_ids,
                "colorCode": tables["ITEM_COLOR"][item_id],
                "additionalItems": additional_items,
            }
        )

    actions = build_actions(tables, raw_mix, raw_result, edition == "cafe")
    stages = []
    for stage_id, stage_name in enumerate(stage_names):
        stages.append(
            {
                "id": stage_id,
                "name": [stage_name, stage_name, stage_name, stage_name],
                "fridge": stage_tables["FRIDGE_LIST"][stage_id],
                "menus": stage_tables["MENU_LIST"][stage_id],
                "hazardMenus": stage_tables["HAZARD_MENU_LIST"][stage_id],
                "weaverMenus": stage_tables["WEAVER_MENU_LIST"][stage_id],
            }
        )

    recipe = {"items": items, "actions": actions, "stages": stages}
    validate_recipe(recipe, item_count, f"{language}/{edition}")
    return recipe


def canonical_sha256(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest().upper()


def source_commit(workshop_repo: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workshop_repo,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    commit = result.stdout.strip()
    return commit if re.fullmatch(r"[0-9a-fA-F]{40}", commit) else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "workshop_repo",
        type=Path,
        help="path to the DoubleJONY/ow_restaurant checkout",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate that committed JSON files exactly match generated output",
    )
    args = parser.parse_args()

    workshop_repo = args.workshop_repo.resolve()
    generated: dict[Path, str] = {}
    summary: dict[str, dict[str, int]] = {}
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "sourceRepository": SOURCE_REPOSITORY,
        "sourceCommit": source_commit(workshop_repo),
        "sources": {},
        "recipes": {},
    }
    for language, file_name in LANGUAGE_FILES.items():
        source_path = workshop_repo / file_name
        if not source_path.is_file():
            raise SystemExit(f"Deluxe source not found: {source_path}")
        source = source_path.read_text(encoding="utf-8")
        summary[language] = {}
        manifest["sources"][language] = {
            "file": file_name,
            "sha256": canonical_sha256(source_path),
        }
        manifest["recipes"][language] = {}
        for edition in EDITION_ITEM_COUNTS:
            recipe = parse_edition(source, language, edition)
            output_path = OUTPUT_DIR / f"recipe-deluxe-{language}-{edition}.json"
            generated[output_path] = json.dumps(recipe, ensure_ascii=False, indent=4) + "\n"
            summary[language][edition] = len(recipe["actions"])
            manifest["recipes"][language][edition] = {
                "file": output_path.name,
                "items": len(recipe["items"]),
                "actions": len(recipe["actions"]),
                "stages": len(recipe["stages"]),
            }

    generated[MANIFEST_PATH] = json.dumps(manifest, ensure_ascii=False, indent=4) + "\n"

    mismatches: list[str] = []
    for output_path, content in generated.items():
        if args.check:
            if not output_path.is_file() or output_path.read_text(encoding="utf-8") != content:
                mismatches.append(str(output_path.relative_to(FRONTEND_ROOT)))
        else:
            output_path.write_text(content, encoding="utf-8")

    if mismatches:
        raise SystemExit("Generated Deluxe data is stale:\n  " + "\n  ".join(mismatches))

    verb = "validated" if args.check else "generated"
    print(f"Deluxe recipes {verb}:")
    for language, editions in summary.items():
        for edition, action_count in editions.items():
            print(
                f"  {language}/{edition}: "
                f"{EDITION_ITEM_COUNTS[edition]} items, {action_count} actions, 12 stages"
            )


if __name__ == "__main__":
    main()
