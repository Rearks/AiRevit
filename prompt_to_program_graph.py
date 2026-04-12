import json
import re
import uuid
import sys
from pathlib import Path
from datetime import date

sys.stdout.reconfigure(encoding='utf-8')

# ── Пути — относительно этого файла ──
_HERE = Path(__file__).resolve().parent
VOCABULARY_FILE = _HERE / "vocabulary.json"
OUTPUT_DIR = _HERE / "dataset" / "generated_program_graphs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FT2_TO_M2 = 0.0929


def load_vocabulary():
    with open(VOCABULARY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def find_phrases_first(text: str, vocab_list: list) -> list:
    """
    Ищем совпадения начиная с длинных фраз.
    Возвращаем список найденных вхождений с позициями.
    """
    found = []
    sorted_vocab = sorted(vocab_list, key=lambda x: len(x), reverse=True)
    for phrase in sorted_vocab:
        for match in re.finditer(re.escape(phrase), text):
            found.append({
                "phrase": phrase,
                "start": match.start(),
                "end": match.end()
            })
    return found


def detect_building_type(text: str, vocab: dict) -> str:
    building_types = vocab.get("building_types", {})
    for kind, synonyms in building_types.items():
        found = find_phrases_first(text, synonyms)
        if found:
            return kind
    return "office"  # default


def detect_area(text: str, vocab: dict) -> tuple:
    """
    Возвращает (area_m2, unit, found).
    Поддерживает форматы: 100 m2 / 100 sq ft / 100 square meters
    """
    area_units = vocab.get("area_units", {})

    # строим паттерн для всех единиц
    all_unit_patterns = []
    for unit_key, synonyms in area_units.items():
        for s in synonyms:
            all_unit_patterns.append((re.escape(s), unit_key))

    # сортируем по длине чтобы длинные фразы шли первыми
    all_unit_patterns.sort(key=lambda x: len(x[0]), reverse=True)

    unit_group = "|".join(p[0] for p in all_unit_patterns)
    pattern = rf"(\d+[\.,]?\d*)\s*({unit_group})"

    match = re.search(pattern, text)
    if not match:
        return None, None, False

    raw_value = match.group(1).replace(",", ".")
    raw_unit = match.group(2)

    area = float(raw_value)

    detected_unit = "m2"
    for pattern_str, unit_key in all_unit_patterns:
        if re.fullmatch(pattern_str, raw_unit):
            detected_unit = unit_key
            break

    if detected_unit == "ft2":
        area = round(area * FT2_TO_M2, 2)

    return area, detected_unit, True


def detect_quantities(text: str, vocab: dict) -> dict:
    """
    Возвращает словарь: {space_kind: count}
    Ищет паттерны типа "two offices", "3 toilets"
    """
    quantities_vocab = vocab.get("quantities", {})
    space_types = vocab.get("space_types", {})
    result = {}

    # строим все синонимы пространства в один плоский список
    all_space_synonyms = []
    for kind, synonyms in space_types.items():
        for s in synonyms:
            all_space_synonyms.append((s, kind))
    all_space_synonyms.sort(key=lambda x: len(x[0]), reverse=True)

    # числовые количества: digit или word
    qty_word_pattern = "|".join(re.escape(w) for w in sorted(quantities_vocab.keys(), key=len, reverse=True))
    qty_pattern = rf"(\d+|{qty_word_pattern})\s+([a-z\s]+?)(?=\s|,|\.|$|and|with)"

    for match in re.finditer(qty_pattern, text):
        raw_qty = match.group(1).strip()
        raw_space = match.group(2).strip()

        # определяем количество
        if raw_qty.isdigit():
            count = int(raw_qty)
        else:
            count = quantities_vocab.get(raw_qty, 1)

        # определяем тип пространства
        detected_kind = None
        for synonym, kind in all_space_synonyms:
            if raw_space.startswith(synonym) or raw_space == synonym:
                detected_kind = kind
                break

        if detected_kind:
            if detected_kind in result:
                result[detected_kind] += count
            else:
                result[detected_kind] = count

    # дополнительно: просто упоминание без числа = 1
    for synonym, kind in all_space_synonyms:
        pattern = rf"\b{re.escape(synonym)}\b"
        if re.search(pattern, text):
            if kind not in result:
                result[kind] = 1

    return result


def detect_ratio(text: str, vocab: dict) -> float:
    ratios = vocab.get("ratios", {})
    sorted_ratios = sorted(ratios.items(), key=lambda x: len(x[0]), reverse=True)
    for phrase, value in sorted_ratios:
        if phrase in text:
            return value
    return None


def detect_constraints(text: str, vocab: dict) -> list:
    constraints_vocab = vocab.get("constraints", {})
    found = []
    for constraint_type, synonyms in constraints_vocab.items():
        for synonym in synonyms:
            if synonym in text:
                found.append(constraint_type)
                break
    return found


def ensure_required_spaces(detected: dict, building_type: str) -> dict:
    """
    Добавляем обязательные помещения если их нет.
    Например для office всегда нужны entrance и corridor.
    """
    required = {
        "office": ["entrance", "corridor", "wc"],
        "restaurant": ["entrance", "dining", "kitchen", "wc"],
        "apartment": ["entrance", "living_room", "wc"],
        "hotel": ["entrance", "corridor", "wc"],
        "clinic": ["entrance", "corridor", "wc"]
    }

    for space in required.get(building_type, ["entrance", "corridor"]):
        if space not in detected:
            detected[space] = 1

    return detected


def build_spaces(detected: dict) -> list:
    spaces = []

    space_display_names = {
        "entrance": "Entrance",
        "corridor": "Corridor",
        "office": "Office",
        "wc": "WC",
        "meeting_room": "Meeting Room",
        "kitchen": "Kitchen",
        "storage": "Storage",
        "open_office": "Open Office",
        "server_room": "Server Room",
        "break_room": "Break Room",
        "reception": "Reception",
        "wardrobe": "Wardrobe",
        "dining": "Dining",
        "bedroom": "Bedroom",
        "living_room": "Living Room"
    }

    # порядок приоритетов — entrance всегда первый, потом corridor
    priority_order = ["entrance", "corridor"]
    ordered_kinds = priority_order + [k for k in detected if k not in priority_order]

    for kind in ordered_kinds:
        if kind not in detected:
            continue

        count = detected[kind]
        display = space_display_names.get(kind, kind.replace("_", " ").title())

        for i in range(count):
            suffix = f"_{i + 1}"
            space_id = f"{kind}{suffix}"
            name = display if count == 1 else f"{display} {i + 1}"

            spaces.append({
                "id": space_id,
                "kind": kind,
                "name": name,
                "name_normalized": kind,
                "area_m2": None,
                "area_source": "to_be_generated",
                "is_required": True,
                "requires_daylight": kind in ("office", "open_office", "meeting_room", "bedroom", "living_room"),
                "is_wet_zone": kind in ("wc", "kitchen"),
                "accessibility_priority": _get_accessibility_priority(kind),
                "confidence": 1.0
            })

    return spaces


def _get_accessibility_priority(kind: str) -> float:
    priorities = {
        "entrance": 1.0,
        "corridor": 1.0,
        "reception": 0.9,
        "office": 0.8,
        "open_office": 0.8,
        "meeting_room": 0.7,
        "wc": 0.6,
        "break_room": 0.6,
        "kitchen": 0.5,
        "storage": 0.4,
        "server_room": 0.3,
        "wardrobe": 0.5,
        "dining": 0.7,
        "bedroom": 0.8,
        "living_room": 0.9
    }
    return priorities.get(kind, 0.5)


def build_connections(spaces: list, building_type: str) -> list:
    """
    Строим стандартные связи в зависимости от типа здания.
    Все помещения соединяются через corridor или entrance.
    """
    connections = []
    conn_id = 1

    space_ids = [s["id"] for s in spaces]
    kinds_present = {s["kind"]: s["id"] for s in spaces}

    corridor_id = kinds_present.get("corridor")
    entrance_id = kinds_present.get("entrance")

    # все offices соединяем с corridor
    # если corridor нет — с entrance
    hub = corridor_id or entrance_id

    if entrance_id and corridor_id:
        connections.append({
            "id": f"c{conn_id}",
            "source": entrance_id,
            "target": corridor_id,
            "connection_type": "direct_access",
            "is_required": True,
            "door_required": False,
            "weight": 1.0
        })
        conn_id += 1

    if hub:
        for space in spaces:
            sid = space["id"]
            skind = space["kind"]

            if sid in (entrance_id, corridor_id):
                continue

            connections.append({
                "id": f"c{conn_id}",
                "source": hub,
                "target": sid,
                "connection_type": "connected_by_door",
                "is_required": True,
                "door_required": True,
                "weight": space["accessibility_priority"]
            })
            conn_id += 1

    return connections


def build_constraints(
    spaces: list,
    total_area: float,
    ratio: float,
    detected_constraints: list
) -> list:
    constraints = []
    c_id = 1

    # total area
    if total_area:
        constraints.append({
            "id": f"k{c_id}",
            "type": "total_area",
            "value": total_area,
            "unit": "m2"
        })
        c_id += 1

    # area ratio между офисами если их 2+
    offices = [s for s in spaces if s["kind"] == "office"]
    if ratio and len(offices) >= 2:
        constraints.append({
            "id": f"k{c_id}",
            "type": "area_ratio",
            "space_a": offices[0]["id"],
            "space_b": offices[1]["id"],
            "value": ratio
        })
        c_id += 1

    # adjacency
    if "must_be_adjacent" in detected_constraints and len(offices) >= 2:
        constraints.append({
            "id": f"k{c_id}",
            "type": "must_be_adjacent",
            "space_a": offices[0]["id"],
            "space_b": offices[1]["id"]
        })
        c_id += 1

    # daylight
    if "requires_daylight" in detected_constraints:
        for space in spaces:
            if space["kind"] in ("office", "open_office", "meeting_room"):
                constraints.append({
                    "id": f"k{c_id}",
                    "type": "requires_daylight",
                    "space_id": space["id"]
                })
                c_id += 1

    return constraints


def build_flows(spaces: list, building_type: str) -> list:
    flows = []

    kinds_present = {}
    for s in spaces:
        if s["kind"] not in kinds_present:
            kinds_present[s["kind"]] = s["id"]

    entrance_id = kinds_present.get("entrance")
    corridor_id = kinds_present.get("corridor")
    wc_id = kinds_present.get("wc")

    offices = [s for s in spaces if s["kind"] == "office"]
    meeting_rooms = [s for s in spaces if s["kind"] == "meeting_room"]

    flow_id = 1

    # Стандартный поток для офиса
    if building_type == "office":
        hub = corridor_id or entrance_id

        for office in offices:
            path = []
            if entrance_id:
                path.append(entrance_id)
            if hub and hub != entrance_id:
                path.append(hub)
            path.append(office["id"])

            if len(path) >= 2:
                flows.append({
                    "id": f"f{flow_id}",
                    "name": f"entry_to_{office['id']}",
                    "path": path,
                    "weight": 1.0,
                    "frequency": "high"
                })
                flow_id += 1

        if wc_id and offices:
            path = []
            path.append(offices[0]["id"])
            if hub:
                path.append(hub)
            path.append(wc_id)

            flows.append({
                "id": f"f{flow_id}",
                "name": f"office_to_wc",
                "path": path,
                "weight": 0.5,
                "frequency": "medium"
            })
            flow_id += 1

    # Стандартный поток для ресторана
    elif building_type == "restaurant":
        dining_id = kinds_present.get("dining")
        kitchen_id = kinds_present.get("kitchen")

        if entrance_id and dining_id:
            flows.append({
                "id": f"f{flow_id}",
                "name": "guest_entry_to_dining",
                "path": [entrance_id, dining_id],
                "weight": 1.0,
                "frequency": "high"
            })
            flow_id += 1

        if dining_id and wc_id:
            flows.append({
                "id": f"f{flow_id}",
                "name": "guest_dining_to_wc",
                "path": [dining_id, wc_id],
                "weight": 0.5,
                "frequency": "medium"
            })
            flow_id += 1

        if dining_id and kitchen_id:
            flows.append({
                "id": f"f{flow_id}",
                "name": "staff_kitchen_to_dining",
                "path": [kitchen_id, dining_id],
                "weight": 0.9,
                "frequency": "high"
            })
            flow_id += 1

    return flows


def build_program_graph(prompt: str, vocab: dict) -> dict:
    text = normalize_text(prompt)

    # Определяем тип здания
    building_type = detect_building_type(text, vocab)

    # Убираем общие фразы, чтобы не двоился счёт (например, "design an office: two offices" -> 3)
    text_for_qty = text.replace("design an office", "").replace("create an office", "").replace("design a small office", "")

    # Определяем площадь
    total_area, unit, area_found = detect_area(text, vocab)

    # Определяем состав помещений
    detected_spaces = detect_quantities(text_for_qty, vocab)

    # Добавляем обязательные помещения
    detected_spaces = ensure_required_spaces(detected_spaces, building_type)

    # Определяем соотношение площадей
    ratio = detect_ratio(text, vocab)

    # Определяем дополнительные ограничения
    detected_constraints = detect_constraints(text, vocab)

    # Строим список помещений
    spaces = build_spaces(detected_spaces)

    # Строим связи
    connections = build_connections(spaces, building_type)

    # Строим ограничения
    constraints = build_constraints(spaces, total_area, ratio, detected_constraints)

    # Строим потоки движения
    flows = build_flows(spaces, building_type)

    # Считаем уникальный ID для этого графа
    graph_id = str(uuid.uuid4())[:8]

    program_graph = {
        "version": "2.0",
        "schema_type": "program_graph",
        "graph_id": graph_id,
        "source": {
            "source_type": "text_prompt",
            "original_prompt": prompt,
            "pdf_file": None,
            "pdf_type": None
        },
        "metadata": {
            "building_type": building_type,
            "floor_number": 1,
            "annotator": "prompt_parser_v1",
            "annotation_date": str(date.today()),
            "quality": "generated",
            "notes": f"Auto-generated from prompt. Area found: {area_found}."
        },
        "spaces": spaces,
        "connections": connections,
        "constraints": constraints,
        "flows": flows,
        "derived": {
            "topology_pattern": building_type,
            "space_count": len(spaces),
            "required_space_count": len([s for s in spaces if s["is_required"]])
        }
    }

    return program_graph


def validate_result(graph: dict) -> list:
    """
    Базовая валидация.
    Возвращает список предупреждений.
    """
    warnings = []

    space_ids = {s["id"] for s in graph.get("spaces", [])}

    # Проверяем все ссылки в connections
    for c in graph.get("connections", []):
        if c["source"] not in space_ids and c["source"] != "outside":
            warnings.append(f"Connection source '{c['source']}' not in spaces")
        if c["target"] not in space_ids:
            warnings.append(f"Connection target '{c['target']}' not in spaces")

    # Проверяем все ссылки в constraints
    for k in graph.get("constraints", []):
        for field in ("space_a", "space_b", "space_id"):
            if field in k and k[field] not in space_ids:
                warnings.append(f"Constraint references unknown space '{k[field]}'")

    # Проверяем все пути в flows
    for f in graph.get("flows", []):
        for pid in f.get("path", []):
            if pid not in space_ids:
                warnings.append(f"Flow '{f['id']}' path contains unknown space '{pid}'")

    # Проверяем что total_area задана
    has_area = any(c.get("type") == "total_area" for c in graph.get("constraints", []))
    if not has_area:
        warnings.append("No total_area constraint found. Area will be estimated by generator.")

    return warnings


def parse_prompt(prompt: str, save: bool = True) -> dict:
    vocab = load_vocabulary()
    graph = build_program_graph(prompt, vocab)
    warnings = validate_result(graph)

    if warnings:
        print("\n[WARNINGS]")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("\n[OK] Validation passed.")

    if save:
        graph_id = graph["graph_id"]
        out_path = OUTPUT_DIR / f"prompt_{graph_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(graph, f, ensure_ascii=False, indent=2)
        print(f"\n[SAVED] {out_path}")

    return graph


def run_from_dynamo(prompt: str, output_dir: str = None) -> str:
    """
    Для вызова из Dynamo Python node.
    Возвращает путь к созданному program_graph.json
    """
    graph = parse_prompt(prompt, save=False)

    graph_id = graph["graph_id"]

    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = OUTPUT_DIR

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"prompt_{graph_id}.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)

    return str(out_path)


def main():
    test_prompts = [
        "Design an office with two offices, total area 100 m², one twice as large, corridor, toilet",
        "Design a small office: three workrooms, meeting room, total area 150 square meters, corridor, restroom, break room",
        "Design a restaurant: dining area, kitchen, two restrooms, total area 200 m², entrance lobby",
        "Create an office with one open office space, server room, reception, washroom, total area 80 sqm"
    ]

    for prompt in test_prompts:
        print(f"\n{'='*60}")
        print(f"PROMPT: {prompt}")
        print("="*60)

        graph = parse_prompt(prompt, save=True)

        print(f"\nBuilding type : {graph['metadata']['building_type']}")
        print(f"Spaces        : {graph['derived']['space_count']}")
        print(f"Connections   : {len(graph['connections'])}")
        print(f"Constraints   : {len(graph['constraints'])}")
        print(f"Flows         : {len(graph['flows'])}")
        print(f"\nSpaces list:")
        for s in graph["spaces"]:
            print(f"  {s['id']:20} kind={s['kind']:15}")


if __name__ == "__main__":
    main()
