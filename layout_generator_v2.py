import json
import math
import copy
from pathlib import Path

BASE_DIR = Path(r"c:\Users\kraer\AiRevit")
INPUT_DIR = BASE_DIR / "dataset" / "generated_program_graphs"
OUTPUT_DIR = BASE_DIR / "dataset" / "layout_solutions_v2"
RULES_FILE = BASE_DIR / "dataset" / "layout_solutions" / "design_rules.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MM2_IN_M2 = 1_000_000

DEFAULT_RULES = {
    "space_rules": {
        "office": {
            "min_small_dim_mm": 3000,
            "min_large_dim_mm": 4500,
            "must_touch_outer_wall": True
        },
        "corridor": {
            "min_small_dim_mm": 1600,
            "preferred_area_ratio": 0.16,
            "min_area_ratio": 0.10,
            "max_area_ratio": 0.22
        },
        "wc": {
            "min_small_dim_mm": 1500,
            "min_large_dim_mm": 1800,
            "preferred_area_m2": 6.0,
            "min_area_m2": 4.0,
            "max_area_m2": 8.0
        }
    },
    "layout_rules": {
        "service_strip_width_candidates_mm": [1800, 2000, 2200, 2400, 2600],
        "boundary_aspect_ratio_min": 0.5,
        "boundary_aspect_ratio_max": 2.0,
        "default_internal_door_width_mm": 900,
        "default_external_door_width_mm": 1000
    },
    "scoring_weights": {
        "required_connection_bonus": 20,
        "required_connection_penalty": -35,
        "adjacency_bonus": 25,
        "adjacency_penalty": -40,
        "outer_wall_bonus": 10,
        "min_dim_penalty": -35,
        "boundary_ratio_penalty": -20,
        "wc_near_entrance_bonus": 8,
        "flow_length_weight": -0.001
    }
}


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def deep_merge(base, custom):
    result = copy.deepcopy(base)
    for k, v in custom.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_rules():
    if RULES_FILE.exists():
        custom = load_json(RULES_FILE)
        return deep_merge(DEFAULT_RULES, custom)
    return copy.deepcopy(DEFAULT_RULES)


def clamp(value, low, high):
    return max(low, min(high, value))


def get_constraint(data, constraint_type):
    for c in data.get("constraints", []):
        if c.get("type") == constraint_type:
            return c
    return None


def get_constraints(data, constraint_type):
    return [c for c in data.get("constraints", []) if c.get("type") == constraint_type]


def get_total_area_m2(data):
    c = get_constraint(data, "total_area")
    if c and c.get("value") is not None:
        return float(c["value"])

    total = 0.0
    for s in data.get("spaces", []):
        if (s.get("kind") or "").lower() == "entrance":
            continue
        area = s.get("area_m2")
        if area is not None:
            total += float(area)
    return total


def classify_spaces(spaces):
    entrance = None
    corridor = None
    offices = []
    wcs = []
    others = []

    for s in spaces:
        kind = (s.get("kind") or "").lower()
        if kind == "entrance":
            entrance = s
        elif kind == "corridor":
            corridor = s
        elif kind == "office":
            offices.append(s)
        elif kind == "wc":
            wcs.append(s)
        else:
            others.append(s)

    return entrance, corridor, offices, wcs, others


def get_area_ratio_constraint_for_offices(data, office_ids):
    constraints = get_constraints(data, "area_ratio")
    for c in constraints:
        a = c.get("space_a")
        b = c.get("space_b")
        value = c.get("value")
        if a in office_ids and b in office_ids and value:
            return {
                "space_a": a,
                "space_b": b,
                "value": float(value)
            }
    return None


def allocate_target_areas(data, rules):
    spaces = data.get("spaces", [])
    entrance, corridor, offices, wcs, others = classify_spaces(spaces)

    if corridor is None:
        raise ValueError("Нет помещения kind='corridor'")
    if len(offices) < 2:
        raise ValueError("Для v2 требуется минимум 2 помещения kind='office'")

    total_area = get_total_area_m2(data)
    if total_area <= 0:
        raise ValueError("Не удалось определить total_area")

    area_map = {}

    # corridor
    corridor_rules = rules["space_rules"]["corridor"]
    corridor_area = total_area * corridor_rules["preferred_area_ratio"]
    corridor_area = clamp(
        corridor_area,
        total_area * corridor_rules["min_area_ratio"],
        total_area * corridor_rules["max_area_ratio"]
    )
    area_map[corridor["id"]] = round(corridor_area, 3)

    # wc
    wc_rules = rules["space_rules"]["wc"]
    for wc in wcs:
        src = wc.get("area_m2")
        if src is not None and total_area < 20:
            wc_area = float(src)
        else:
            wc_area = wc_rules["preferred_area_m2"]

        wc_area = clamp(
            wc_area,
            wc_rules["min_area_m2"],
            wc_rules["max_area_m2"]
        )
        area_map[wc["id"]] = round(wc_area, 3)

    # others (если будут)
    # Пока просто берем source-площади как есть, если они есть
    for s in others:
        if (s.get("kind") or "").lower() == "entrance":
            continue
        src = s.get("area_m2")
        if src is not None:
            area_map[s["id"]] = float(src)

    reserved = sum(area_map.values())
    remaining = total_area - reserved

    if remaining <= 0:
        raise ValueError(
            f"После corridor/wc/others не осталось площади под офисы. "
            f"total={total_area}, reserved={reserved}"
        )

    office_ids = [o["id"] for o in offices]
    ratio_constraint = get_area_ratio_constraint_for_offices(data, office_ids)

    if len(offices) == 2 and ratio_constraint:
        a = ratio_constraint["space_a"]
        b = ratio_constraint["space_b"]
        r = ratio_constraint["value"]  # area(a) = r * area(b)

        b_area = remaining / (r + 1.0)
        a_area = remaining - b_area
        area_map[a] = round(a_area, 3)
        area_map[b] = round(b_area, 3)
    else:
        # если ratio нет — распределяем по исходным площадям, либо поровну
        source_sum = 0.0
        source_map = {}
        for o in offices:
            src = o.get("area_m2")
            if src is not None and float(src) > 0:
                source_map[o["id"]] = float(src)
                source_sum += float(src)

        if source_sum > 0:
            assigned = 0.0
            for i, o in enumerate(offices):
                oid = o["id"]
                if i < len(offices) - 1:
                    area = remaining * (source_map.get(oid, 1.0) / source_sum)
                    area_map[oid] = round(area, 3)
                    assigned += area_map[oid]
                else:
                    area_map[oid] = round(remaining - assigned, 3)
        else:
            each = remaining / len(offices)
            assigned = 0.0
            for i, o in enumerate(offices):
                oid = o["id"]
                if i < len(offices) - 1:
                    area_map[oid] = round(each, 3)
                    assigned += area_map[oid]
                else:
                    area_map[oid] = round(remaining - assigned, 3)

    # Финальная коррекция последнего офиса, чтобы сумма совпала идеально
    non_entrance_ids = [
        s["id"] for s in spaces
        if (s.get("kind") or "").lower() != "entrance"
    ]
    current_sum = sum(area_map.get(i, 0.0) for i in non_entrance_ids)
    delta = round(total_area - current_sum, 3)
    if abs(delta) > 0 and offices:
        area_map[offices[-1]["id"]] = round(area_map[offices[-1]["id"]] + delta, 3)

    return total_area, area_map


def rect_room(space, x, y, w, h, target_area):
    return {
        "id": space["id"],
        "kind": space.get("kind"),
        "name": space.get("name", space["id"]),
        "x_mm": round(x, 1),
        "y_mm": round(y, 1),
        "width_mm": round(w, 1),
        "height_mm": round(h, 1),
        "target_area_m2": round(target_area, 3),
        "generated_area_m2": round((w * h) / MM2_IN_M2, 3)
    }


def room_center(room):
    return (
        room["x_mm"] + room["width_mm"] / 2.0,
        room["y_mm"] + room["height_mm"] / 2.0
    )


def shared_boundary_length(a, b, eps=1e-6):
    ax1, ay1 = a["x_mm"], a["y_mm"]
    ax2, ay2 = ax1 + a["width_mm"], ay1 + a["height_mm"]
    bx1, by1 = b["x_mm"], b["y_mm"]
    bx2, by2 = bx1 + b["width_mm"], by1 + b["height_mm"]

    # вертикальная общая граница
    if abs(ax2 - bx1) < eps or abs(bx2 - ax1) < eps:
        overlap = min(ay2, by2) - max(ay1, by1)
        return max(0.0, overlap)

    # горизонтальная общая граница
    if abs(ay2 - by1) < eps or abs(by2 - ay1) < eps:
        overlap = min(ax2, bx2) - max(ax1, bx1)
        return max(0.0, overlap)

    return 0.0


def touches_outer_wall(room, boundary, eps=1e-6):
    x1 = room["x_mm"]
    y1 = room["y_mm"]
    x2 = x1 + room["width_mm"]
    y2 = y1 + room["height_mm"]

    bx1 = boundary["x_mm"]
    by1 = boundary["y_mm"]
    bx2 = bx1 + boundary["width_mm"]
    by2 = by1 + boundary["height_mm"]

    return (
        abs(x1 - bx1) < eps or
        abs(y1 - by1) < eps or
        abs(x2 - bx2) < eps or
        abs(y2 - by2) < eps
    )


def get_min_dim_rules(kind, rules):
    kind = (kind or "").lower()
    if kind == "office":
        return rules["space_rules"]["office"]["min_small_dim_mm"], rules["space_rules"]["office"]["min_large_dim_mm"]
    if kind == "wc":
        return rules["space_rules"]["wc"]["min_small_dim_mm"], rules["space_rules"]["wc"]["min_large_dim_mm"]
    if kind == "corridor":
        m = rules["space_rules"]["corridor"]["min_small_dim_mm"]
        return m, m
    return 1000, 1000


def add_external_door(corridor_room, rules):
    width = rules["layout_rules"]["default_external_door_width_mm"]
    x = corridor_room["x_mm"] + corridor_room["width_mm"] / 2.0 - width / 2.0
    y = corridor_room["y_mm"]  # нижняя граница коридора
    return {
        "id": "door_entrance",
        "type": "external_door",
        "from": "outside",
        "to": corridor_room["id"],
        "x_mm": round(x, 1),
        "y_mm": round(y, 1),
        "width_mm": width,
        "orientation": "horizontal"
    }


def add_door_vertical_edge(left_room, right_room, rules, door_id):
    """
    Дверь на общей вертикальной границе между двумя прямоугольниками.
    """
    door_width = rules["layout_rules"]["default_internal_door_width_mm"]
    x = left_room["x_mm"] + left_room["width_mm"]

    overlap_start = max(left_room["y_mm"], right_room["y_mm"])
    overlap_end = min(
        left_room["y_mm"] + left_room["height_mm"],
        right_room["y_mm"] + right_room["height_mm"]
    )
    overlap = overlap_end - overlap_start

    if overlap <= 0:
        return None

    usable = max(door_width, min(overlap, door_width))
    y = overlap_start + (overlap - usable) / 2.0

    return {
        "id": door_id,
        "type": "internal_door",
        "from": left_room["id"],
        "to": right_room["id"],
        "x_mm": round(x, 1),
        "y_mm": round(y, 1),
        "width_mm": round(usable, 1),
        "orientation": "vertical"
    }


def add_door_horizontal_edge(lower_room, upper_room, rules, door_id):
    """
    Дверь на общей горизонтальной границе между двумя прямоугольниками.
    """
    door_width = rules["layout_rules"]["default_internal_door_width_mm"]
    y = lower_room["y_mm"] + lower_room["height_mm"]

    overlap_start = max(lower_room["x_mm"], upper_room["x_mm"])
    overlap_end = min(
        lower_room["x_mm"] + lower_room["width_mm"],
        upper_room["x_mm"] + upper_room["width_mm"]
    )
    overlap = overlap_end - overlap_start

    if overlap <= 0:
        return None

    usable = max(door_width, min(overlap, door_width))
    x = overlap_start + (overlap - usable) / 2.0

    return {
        "id": door_id,
        "type": "internal_door",
        "from": lower_room["id"],
        "to": upper_room["id"],
        "x_mm": round(x, 1),
        "y_mm": round(y, 1),
        "width_mm": round(usable, 1),
        "orientation": "horizontal"
    }


def generate_template_left_service_stack(data, area_map, rules, service_strip_width_mm):
    spaces = data.get("spaces", [])
    entrance, corridor, offices, wcs, others = classify_spaces(spaces)

    if corridor is None or len(offices) < 2:
        raise ValueError("Шаблон left_service_stack требует corridor + 2 offices")

    service_spaces = wcs + others  # пока wc сверху над corridor

    corridor_area_mm2 = area_map[corridor["id"]] * MM2_IN_M2
    service_area_total_mm2 = sum(area_map[s["id"]] * MM2_IN_M2 for s in service_spaces)
    office_area_total_mm2 = sum(area_map[o["id"]] * MM2_IN_M2 for o in offices)

    corridor_h = corridor_area_mm2 / service_strip_width_mm
    boundary_h = (corridor_area_mm2 + service_area_total_mm2) / service_strip_width_mm

    if boundary_h <= 0:
        raise ValueError("boundary_h <= 0")

    right_w = office_area_total_mm2 / boundary_h
    if right_w <= 0:
        raise ValueError("right_w <= 0")

    boundary_w = service_strip_width_mm + right_w

    rooms = []

    # corridor внизу слева
    corridor_room = rect_room(
        corridor,
        0.0, 0.0,
        service_strip_width_mm,
        corridor_h,
        area_map[corridor["id"]]
    )
    rooms.append(corridor_room)

    # service rooms над corridor
    y_cursor = corridor_h
    for s in service_spaces:
        area_mm2 = area_map[s["id"]] * MM2_IN_M2
        h = area_mm2 / service_strip_width_mm
        r = rect_room(
            s,
            0.0, y_cursor,
            service_strip_width_mm,
            h,
            area_map[s["id"]]
        )
        rooms.append(r)
        y_cursor += h

    # offices справа, снизу вверх, от меньшего к большему,
    # чтобы оба максимально имели доступ к corridor
    offices_sorted = sorted(offices, key=lambda x: area_map[x["id"]])
    y_cursor = 0.0
    for i, o in enumerate(offices_sorted):
        if i < len(offices_sorted) - 1:
            area_mm2 = area_map[o["id"]] * MM2_IN_M2
            h = area_mm2 / right_w
        else:
            h = boundary_h - y_cursor  # замыкаем точно в границу

        r = rect_room(
            o,
            service_strip_width_mm, y_cursor,
            right_w, h,
            area_map[o["id"]]
        )
        rooms.append(r)
        y_cursor += h

    room_map = {r["id"]: r for r in rooms}

    openings = []
    openings.append(add_external_door(corridor_room, rules))

    # corridor -> service rooms
    for s in service_spaces:
        s_room = room_map[s["id"]]
        if shared_boundary_length(corridor_room, s_room) >= rules["layout_rules"]["default_internal_door_width_mm"]:
            door = add_door_horizontal_edge(
                corridor_room, s_room, rules,
                f"door_{corridor_room['id']}_{s_room['id']}"
            )
            if door:
                openings.append(door)

    # corridor -> offices
    for o in offices_sorted:
        o_room = room_map[o["id"]]
        if shared_boundary_length(corridor_room, o_room) >= rules["layout_rules"]["default_internal_door_width_mm"]:
            door = add_door_vertical_edge(
                corridor_room, o_room, rules,
                f"door_{corridor_room['id']}_{o_room['id']}"
            )
            if door:
                openings.append(door)

    layout = {
        "version": "2.0",
        "schema_type": "layout_solution",
        "generator": {
            "name": "layout_generator_v2",
            "template": "left_service_stack",
            "service_strip_width_mm": service_strip_width_mm
        },
        "units": "mm",
        "boundary": {
            "x_mm": 0.0,
            "y_mm": 0.0,
            "width_mm": round(boundary_w, 1),
            "height_mm": round(boundary_h, 1)
        },
        "rooms": rooms,
        "openings": openings
    }

    return layout


def score_layout(layout, data, rules):
    score = 0.0
    warnings = []

    weights = rules["scoring_weights"]
    boundary = layout["boundary"]
    room_map = {r["id"]: r for r in layout["rooms"]}

    # 1. Проверка минимальных размеров
    for room in layout["rooms"]:
        small = min(room["width_mm"], room["height_mm"])
        large = max(room["width_mm"], room["height_mm"])
        min_small, min_large = get_min_dim_rules(room["kind"], rules)

        if small < min_small or large < min_large:
            score += weights["min_dim_penalty"]
            warnings.append(
                f"Room {room['id']} below min dims: "
                f"{room['width_mm']} x {room['height_mm']} mm"
            )

    # 2. Обязательные связи
    for c in data.get("connections", []):
        src = c.get("source")
        tgt = c.get("target")
        ctype = c.get("connection_type", c.get("type"))
        is_required = c.get("is_required", True)

        if not is_required:
            continue

        # entrance -> corridor
        if src not in room_map or tgt not in room_map:
            if ctype in ("direct_access", "connected_by_door"):
                # если одна из точек — entrance, считаем, что external door решает
                if ((src and "entrance" in src) or (tgt and "entrance" in tgt)):
                    score += weights["required_connection_bonus"]
                else:
                    score += weights["required_connection_penalty"]
            continue

        shared = shared_boundary_length(room_map[src], room_map[tgt])
        if shared >= rules["layout_rules"]["default_internal_door_width_mm"]:
            score += weights["required_connection_bonus"]
        else:
            score += weights["required_connection_penalty"]

    # 3. Adjacency constraints
    for c in data.get("constraints", []):
        if c.get("type") == "must_be_adjacent":
            a = c.get("space_a")
            b = c.get("space_b")
            if a in room_map and b in room_map:
                shared = shared_boundary_length(room_map[a], room_map[b])
                if shared > 0:
                    score += weights["adjacency_bonus"]
                else:
                    score += weights["adjacency_penalty"]

    # 4. Офисы должны касаться внешней стены
    for room in layout["rooms"]:
        if (room.get("kind") or "").lower() == "office":
            if touches_outer_wall(room, boundary):
                score += weights["outer_wall_bonus"]

    # 5. Пропорции общего контура
    ratio = boundary["width_mm"] / boundary["height_mm"] if boundary["height_mm"] else 1.0
    min_ratio = rules["layout_rules"]["boundary_aspect_ratio_min"]
    max_ratio = rules["layout_rules"]["boundary_aspect_ratio_max"]
    if ratio < min_ratio or ratio > max_ratio:
        score += weights["boundary_ratio_penalty"]
        warnings.append(f"Boundary aspect ratio out of preferred range: {round(ratio, 3)}")

    # 6. wc ближе к входу — небольшой бонус
    entrance_point = None
    for op in layout.get("openings", []):
        if op.get("type") == "external_door":
            if op.get("orientation") == "horizontal":
                entrance_point = (op["x_mm"] + op["width_mm"] / 2.0, op["y_mm"])
            else:
                entrance_point = (op["x_mm"], op["y_mm"] + op["width_mm"] / 2.0)
            break

    if entrance_point:
        for room in layout["rooms"]:
            if (room.get("kind") or "").lower() == "wc":
                cx, cy = room_center(room)
                dist = math.dist(entrance_point, (cx, cy))
                # чем ближе, тем лучше; грубый бонус
                if dist < boundary["height_mm"] * 0.75:
                    score += weights["wc_near_entrance_bonus"]

    # 7. Штраф за длинные flow-маршруты
    points = {rid: room_center(r) for rid, r in room_map.items()}
    if entrance_point:
        for s in data.get("spaces", []):
            if (s.get("kind") or "").lower() == "entrance":
                points[s["id"]] = entrance_point

    for flow in data.get("flows", []):
        path = flow.get("path", [])
        for i in range(len(path) - 1):
            a = path[i]
            b = path[i + 1]
            if a in points and b in points:
                d = math.dist(points[a], points[b])
                score += weights["flow_length_weight"] * d

    return round(score, 3), warnings


def generate_best_layout(data, rules):
    total_area, area_map = allocate_target_areas(data, rules)

    candidates = []
    widths = rules["layout_rules"]["service_strip_width_candidates_mm"]

    for strip_w in widths:
        try:
            layout = generate_template_left_service_stack(data, area_map, rules, strip_w)
            score, warnings = score_layout(layout, data, rules)

            generated_total = sum(r["generated_area_m2"] for r in layout["rooms"])

            layout["metrics"] = {
                "target_total_area_m2": round(total_area, 3),
                "generated_total_area_m2": round(generated_total, 3),
                "room_count": len(layout["rooms"]),
                "opening_count": len(layout["openings"]),
                "score": score
            }
            layout["warnings"] = warnings

            candidates.append(layout)

        except Exception as e:
            candidates.append({
                "generator": {
                    "name": "layout_generator_v2",
                    "template": "left_service_stack",
                    "service_strip_width_mm": strip_w
                },
                "failed": True,
                "error": str(e)
            })

    valid = [c for c in candidates if not c.get("failed")]
    if not valid:
        raise ValueError("Все кандидаты layout failed")

    best = max(valid, key=lambda x: x["metrics"]["score"])

    best["candidate_scores"] = [
        {
            "service_strip_width_mm": c["generator"]["service_strip_width_mm"],
            "score": c["metrics"]["score"]
        }
        for c in valid
    ]

    best["generator"]["area_map_m2"] = area_map

    source_pdf = data.get("source", {}).get("pdf_file", "unknown")
    best["generator"]["source_program_graph"] = source_pdf

    return best


def main():
    rules = load_rules()
    files = sorted(INPUT_DIR.glob("*.json"))

    if not files:
        print(f"Нет JSON-файлов в {INPUT_DIR}")
        return

    ok = 0
    failed = 0

    for path in files:
        try:
            data = load_json(path)
            layout = generate_best_layout(data, rules)

            out_path = OUTPUT_DIR / path.name.replace(".json", "_layout_v2.json")
            save_json(out_path, layout)

            print(
                f"[OK] {path.name} -> {out_path.name} | "
                f"score={layout['metrics']['score']} | "
                f"boundary={layout['boundary']['width_mm']}x{layout['boundary']['height_mm']} mm"
            )
            ok += 1

        except Exception as e:
            print(f"[FAIL] {path.name}: {e}")
            failed += 1

    print("\n--- SUMMARY ---")
    print(f"Generated: {ok}")
    print(f"Failed:    {failed}")


if __name__ == "__main__":
    main()
