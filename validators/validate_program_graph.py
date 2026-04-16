"""
validate_program_graph.py
Validates a program_graph.json file against the AiRevit v2.0 schema.

Usage:
    python validators/validate_program_graph.py <path_to_file.json>
    python validators/validate_program_graph.py dataset/generated_program_graphs/

If a directory is passed, all .json files in it will be validated.
"""

import sys
import json
import os

REQUIRED_ROOT_KEYS = {"version", "prompt", "spaces", "connections"}
REQUIRED_SPACE_KEYS = {"id", "type", "area_m2"}
REQUIRED_CONNECTION_KEYS = {"from", "to"}

def validate_file(path):
    errors = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return [f"Cannot parse JSON: {e}"]

    # Root keys
    missing_root = REQUIRED_ROOT_KEYS - set(data.keys())
    if missing_root:
        errors.append(f"Missing root keys: {missing_root}")

    # Spaces
    for i, space in enumerate(data.get("spaces", [])):
        missing = REQUIRED_SPACE_KEYS - set(space.keys())
        if missing:
            errors.append(f"Space[{i}] missing keys: {missing}")

    # Connections
    for i, conn in enumerate(data.get("connections", [])):
        missing = REQUIRED_CONNECTION_KEYS - set(conn.keys())
        if missing:
            errors.append(f"Connection[{i}] missing keys: {missing}")

    return errors


def validate_path(target):
    if os.path.isdir(target):
        files = [os.path.join(target, f) for f in os.listdir(target) if f.endswith(".json")]
    elif os.path.isfile(target):
        files = [target]
    else:
        print(f"ERROR: Path not found: {target}")
        sys.exit(1)

    if not files:
        print("No JSON files found.")
        sys.exit(0)

    all_ok = True
    for f in files:
        errors = validate_file(f)
        if errors:
            all_ok = False
            print(f"FAIL  {f}")
            for e in errors:
                print(f"      - {e}")
        else:
            print(f"OK    {f}")

    print()
    if all_ok:
        print(f"All {len(files)} file(s) passed validation.")
        sys.exit(0)
    else:
        print("Validation failed. Fix errors before submitting a PR.")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    validate_path(sys.argv[1])
