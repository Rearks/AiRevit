import json
import math
from pathlib import Path

INPUT_DIR = Path("dataset/annotations")
OUTPUT_DIR = Path("dataset/layout_solutions")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MM2_IN_M2 = 1_000_000

# Базовые параметры генерации
DEFAULT_DOOR_WIDTH_MM = 900
MIN_CORRIDOR_WIDTH_MM = 1800
DEFAULT_ASPECT_RATIO = 1.2  # width / height
GENERATOR_NAME = "layout_generator_v1"


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_constraint(data, constraint_type):
    for c in data.get("constraints", []):
        if c.get("type") == constraint_type:
            return c
    return None


def get_total_area_m2(data):
    c = get_constraint(data, "total_area")
    if c and c.get("value") is not None:
        return float(c["value"])

    total = 0.0
    for s in data.get("spaces", []):
        if s.get("kind") == "entrance":
            continue
        area = s.get("area_m2")
        if area is not None:
            total += float(area)
    return total


def get_spaces(data):
    return data.get("spaces", [])


def scale_room_areas(spaces, target_total_area_m2):
    """
    Масштабируем известные площади помещений под target_total_area_m2.
    entrance не учитываем.
    """
    area_spaces = []
    base_sum = 0.0

    for s in spaces:
        if s.get("kind") == "entrance":
            continue
        area = s.get("area_m2")
        if area is not None:
            base_sum += float(area)
        area_spaces.append(s)

    if base_sum <= 0:
        raise ValueError("Сумма площадей помещений равна 0 — нечего масштабировать.")

    scale = target_total_area_m2 / base_sum

    scaled = []
    for s in area_spaces:
        area = s.get("area_m2")
        if area is None:
            raise ValueError(f"У помещения {s.get('id')} нет area_m2.")
        new_s = dict(s)
        new_s["target_area_m2"] = float(area) * scale
        scaled.append(new_s)

    return scaled, scale


def classify_spaces(spaces):
    entrance = None
    corridor = None
    offices = []
    wc_spaces = []
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
            wc_spaces.append(s)
        else:
            others.append(s)

    return entrance, corridor, offices, wc_spaces, others


def choose_boundary(total_area_m2, corridor_area_m2):
    """
    Выбираем внешний прямоугольник.
    Сначала пытаемся взять aspect ratio ~ 1.2,
    потом проверяем, чтобы коридор не был уже MIN_CORRIDOR_WIDTH_MM.
    """
    total_area_mm2 = total_area_m2 * MM2_IN_M2
    corridor_area_mm2 = corridor_area_m2 * MM2_IN_M2

    # Базовый вариант
    height = math.sqrt(total_area_mm2 / DEFAULT_ASPECT_RATIO)
    width = total_area_mm2 / height

    corridor_width = corridor_area_mm2 / height

    # Если коридор слишком узкий — уменьшаем высоту, чтобы коридор стал шире
    if corridor_width < MIN_CORRIDOR_WIDTH_MM:
        height = corridor_area_mm2 / MIN_CORRIDOR_WIDTH_MM
        width = total_area_mm2 / height
        corridor_width = corridor_area_mm2 / height

    return round(width, 1), round(height, 1), round(corridor_width, 1)


def generate_layout(data):
    source_pdf = data.get("source", {}).get("pdf_file", "unknown.json")
    spaces = get_spaces(data)

    entrance, corridor, offices, wc_spaces, others = classify_spaces(spaces)

    if corridor is None:
        raise ValueError("В графе нет corridor — текущий генератор требует хотя бы один коридор.")

    if len(offices) < 1:
        raise ValueError("В графе нет office — текущий генератор требует хотя бы один офис.")

    target_total_area_m2 = get_total_area_m2(data)
    scaled_spaces, scale = scale_room_areas(spaces, target_total_area_m2)

    # Переклассифицируем уже масштабированные пространства
    entrance_s, corridor_s, offices_s, wc_s, others_s = classify_spaces(scaled_spaces)

    # Сортируем офисы по убыванию площади
    offices_s = sorted(offices_s, key=lambda x: x["target_area_m2"], reverse=True)

    corridor_area_m2 = corridor_s["target_area_m2"]

    boundary_w, boundary_h, corridor_w = choose_boundary(target_total_area_m2, corridor_area_m2)
    total_area_mm2 = target_total_area_m2 * MM2_IN_M2

    # Коридор занимает всю высоту
    # Остальные помещения ставим справа вертикальным стеком.
    right_w = boundary_w - corridor_w
    if right_w <= 0:
        raise ValueError("Не удалось вычислить ширину правой зоны.")

    placed_rooms = []
    warnings = []

    # 1. Коридор
    corridor_rect = {
        "id": corridor_s["id"],
        "kind": corridor_s["kind"],
        "name": corridor_s.get("name"),
        "x_mm": 0.0,
        "y_mm": 0.0,
        "width_mm": corridor_w,
        "height_mm": boundary_h,
        "target_area_m2": round(corridor_s["target_area_m2"], 3),
        "generated_area_m2": round((corridor_w * boundary_h) / MM2_IN_M2, 3)
    }
    placed_rooms.append(corridor_rect)

    # 2. Все остальные справа
    # Порядок:
    # - сначала офисы (чтобы они были смежны),
    # - потом wc,
    # - потом прочие помещения.
    stack = offices_s + wc_s + others_s

    y_cursor = 0.0
    for room in stack:
        area_mm2 = room["target_area_m2"] * MM2_IN_M2
        room_h = area_mm2 / right_w

        rect = {
            "id": room["id"],
            "kind": room["kind"],
            "name": room.get("name"),
            "x_mm": corridor_w,
            "y_mm": round(y_cursor, 1),
            "width_mm": round(right_w, 1),
            "height_mm": round(room_h, 1),
            "target_area_m2": round(room["target_area_m2"], 3),
            "generated_area_m2": round((right_w * room_h) / MM2_IN_M2, 3)
        }
        placed_rooms.append(rect)

        # Простая проверка на слишком тонкие помещения
        if min(rect["width_mm"], rect["height_mm"]) < 1200:
            warnings.append(
                f"Помещение {room['id']} получилось слишком узким/низким: "
                f"{rect['width_mm']} x {rect['height_mm']} мм"
            )

        y_cursor += room_h

    # Небольшая коррекция последнего помещения, чтобы сумма по высоте совпала точно
    if len(stack) > 0:
        top = placed_rooms[-1]
        current_sum = top["y_mm"] + top["height_mm"]
        delta = round(boundary_h - current_sum, 1)
        top["height_mm"] = round(top["height_mm"] + delta, 1)
        top["generated_area_m2"] = round((top["width_mm"] * top["height_mm"]) / MM2_IN_M2, 3)

    # 3. Двери
    openings = []

    # Входная дверь изнаружи в коридор
    if entrance is not None:
        openings.append({
            "id": "door_entrance",
            "type": "external_door",
            "from": "outside",
            "to": corridor_s["id"],
            "x_mm": round(corridor_w / 2 - DEFAULT_DOOR_WIDTH_MM / 2, 1),
            "y_mm": 0.0,
            "width_mm": DEFAULT_DOOR_WIDTH_MM,
            "orientation": "horizontal"
        })

    # Внутренние двери: corridor -> каждое помещение справа
    for room in placed_rooms:
        if room["id"] == corridor_s["id"]:
            continue

        door_y = round(room["y_mm"] + room["height_mm"] / 2 - DEFAULT_DOOR_WIDTH_MM / 2, 1)

        openings.append({
            "id": f"door_{corridor_s['id']}_{room['id']}",
            "type": "internal_door",
            "from": corridor_s["id"],
            "to": room["id"],
            "x_mm": round(corridor_w, 1),
            "y_mm": door_y,
            "width_mm": DEFAULT_DOOR_WIDTH_MM,
            "orientation": "vertical"
        })

    # 4. Метрики
    generated_total_area = sum(r["generated_area_m2"] for r in placed_rooms)

    layout = {
        "version": "1.0",
        "schema_type": "layout_solution",
        "generator": {
            "name": GENERATOR_NAME,
            "strategy": "rectangular_template_baseline",
            "source_program_graph": source_pdf,
            "scale_factor_from_annotation": round(scale, 4)
        },
        "units": "mm",
        "boundary": {
            "x_mm": 0.0,
            "y_mm": 0.0,
            "width_mm": round(boundary_w, 1),
            "height_mm": round(boundary_h, 1)
        },
        "rooms": placed_rooms,
        "openings": openings,
        "metrics": {
            "target_total_area_m2": round(target_total_area_m2, 3),
            "generated_total_area_m2": round(generated_total_area, 3),
            "room_count": len(placed_rooms),
            "opening_count": len(openings)
        },
        "warnings": warnings
    }

    return layout


def main():
    files = sorted(INPUT_DIR.glob("*.json"))
    if not files:
        print(f"Нет JSON-файлов в {INPUT_DIR}")
        return

    ok = 0
    failed = 0

    for path in files:
        try:
            data = load_json(path)
            layout = generate_layout(data)

            out_path = OUTPUT_DIR / path.name.replace(".json", "_layout.json")
            save_json(out_path, layout)

            print(f"[OK] {path.name} -> {out_path.name}")
            ok += 1

        except Exception as e:
            print(f"[FAIL] {path.name}: {e}")
            failed += 1

    print("\n--- SUMMARY ---")
    print(f"Generated: {ok}")
    print(f"Failed:    {failed}")


if __name__ == "__main__":
    main()
