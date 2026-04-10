# -*- coding: utf-8 -*-
# NODE 3B — Validate Topology
# IN[0] : dict - Output from Node 3A
# OUT   : dict - same structure as Node 3A output (pass-through if valid)
#
# Validate topology BEFORE compiling to action plan.
# If valid   → status "ok", topology passes through to Node 4A
# If warning → status "ok", warnings added, still passes through
# If error   → status "error", topology blocked from execution
#
# Pipeline: Node 3A → [Node 3B] → Node 4A → Node 4B → Node 5
#
# BIM Semantics v1:
#   - Размеры по оси стен (centerline)
#   - Одна общая стена между помещениями
#   - Все стены room-bounding
#   - Только пустое место (нет существующей геометрии)
#   - Один уровень

import traceback

OUT = {"status": "Node 3B: не запущен"}

EPS = 1e-3  # допуск для float-сравнений (мм)

try:
    string_types = (basestring,)
except:
    string_types = (str,)

# =============================================
# УТИЛИТЫ
# =============================================

def _is_string(x):
    return isinstance(x, string_types)

def _as_py(obj):
    """Преобразует .NET collections в обычные Python dict/list."""
    if obj is None:
        return None

    if isinstance(obj, dict):
        d = {}
        for k, v in obj.items():
            d[str(k)] = _as_py(v)
        return d

    if isinstance(obj, (list, tuple)):
        return [_as_py(x) for x in obj]

    if _is_string(obj):
        return obj

    # .NET Dictionary
    if hasattr(obj, "Keys") and hasattr(obj, "__getitem__"):
        try:
            d = {}
            for k in obj.Keys:
                d[str(k)] = _as_py(obj[k])
            return d
        except:
            pass

    # .NET List / IList
    if hasattr(obj, "Count") and hasattr(obj, "__getitem__"):
        try:
            return [_as_py(obj[i]) for i in range(obj.Count)]
        except:
            pass

    return obj

def _get(d, key, default=None):
    try:
        if hasattr(d, "get"):
            return d.get(key, default)
    except:
        pass
    try:
        return d[key]
    except:
        return default

def _to_float(v, d=None):
    try:
        return float(v)
    except:
        return d

def _is_positive(v):
    try:
        return float(v) > 0
    except:
        return False

# =============================================
# ГЕОМЕТРИЧЕСКИЕ ПРОВЕРКИ
# =============================================

def _rect_from_space(sp):
    """Извлечь x, y, w, h из space.rect."""
    rect = _as_py(_get(sp, "rect", {}))
    if not isinstance(rect, dict):
        return None, None, None, None

    x = _to_float(_get(rect, "x_mm", 0), None)
    y = _to_float(_get(rect, "y_mm", 0), None)
    w = _to_float(_get(rect, "width_mm", 0), None)
    h = _to_float(_get(rect, "length_mm", 0), None)
    return x, y, w, h

def _point_inside_rect(px, py, x, y, w, h):
    """Проверяет, что точка (px, py) строго внутри прямоугольника."""
    return (x + EPS < px < x + w - EPS) and (y + EPS < py < y + h - EPS)

def _point_inside_or_on_rect(px, py, x, y, w, h):
    """Проверяет, что точка (px, py) внутри или на границе прямоугольника."""
    return (x - EPS <= px <= x + w + EPS) and (y - EPS <= py <= y + h + EPS)

def _rects_overlap(x1, y1, w1, h1, x2, y2, w2, h2):
    """
    Проверяет, что два прямоугольника пересекаются по площади
    (не просто касаются границами).
    Касание границами — это нормально (общая стена).
    """
    # Нет пересечения если один полностью слева/справа/выше/ниже другого
    if x1 + w1 <= x2 + EPS:
        return False
    if x2 + w2 <= x1 + EPS:
        return False
    if y1 + h1 <= y2 + EPS:
        return False
    if y2 + h2 <= y1 + EPS:
        return False
    return True

def _segment_on_rect_edge(seg_p1, seg_p2, x, y, w, h):
    """
    Проверяет, что сегмент [[x1,y1],[x2,y2]] лежит на одной
    из четырёх сторон прямоугольника (x, y, w, h).
    """
    sx1 = _to_float(seg_p1[0], None)
    sy1 = _to_float(seg_p1[1], None)
    sx2 = _to_float(seg_p2[0], None)
    sy2 = _to_float(seg_p2[1], None)

    if sx1 is None or sy1 is None or sx2 is None or sy2 is None:
        return False

    edges = [
        # bottom: y=y, x from x to x+w
        ("H", y, x, x + w),
        # top: y=y+h, x from x to x+w
        ("H", y + h, x, x + w),
        # left: x=x, y from y to y+h
        ("V", x, y, y + h),
        # right: x=x+w, y from y to y+h
        ("V", x + w, y, y + h),
    ]

    for orientation, coord, a_min, a_max in edges:
        if orientation == "H":
            # Горизонтальное ребро: оба y координаты сегмента == coord
            if abs(sy1 - coord) < EPS and abs(sy2 - coord) < EPS:
                # и x координаты сегмента в пределах ребра
                seg_min = min(sx1, sx2)
                seg_max = max(sx1, sx2)
                if seg_min >= a_min - EPS and seg_max <= a_max + EPS:
                    return True
        else:
            # Вертикальное ребро: оба x координаты сегмента == coord
            if abs(sx1 - coord) < EPS and abs(sx2 - coord) < EPS:
                seg_min = min(sy1, sy2)
                seg_max = max(sy1, sy2)
                if seg_min >= a_min - EPS and seg_max <= a_max + EPS:
                    return True

    return False

# =============================================
# ВАЛИДАЦИИ
# =============================================

def validate_spaces_structure(spaces, errors, warnings):
    """Проверяет структуру каждого space: наличие полей, типы."""
    if not isinstance(spaces, list):
        errors.append("'spaces' не является списком")
        return

    if not spaces:
        errors.append("'spaces' пуст — нет помещений для построения")
        return

    ids_seen = set()

    for i, sp in enumerate(spaces):
        sp = _as_py(sp)
        if not isinstance(sp, dict):
            errors.append("Space #{} не является словарём".format(i + 1))
            continue

        sid = str(_get(sp, "id", "")).strip()
        label = "Space '{}' (#{})".format(sid, i + 1) if sid else "Space #{}".format(i + 1)

        # id
        if not sid:
            errors.append("{}: отсутствует 'id'".format(label))
        elif sid in ids_seen:
            errors.append("{}: дублирующийся id '{}'".format(label, sid))
        else:
            ids_seen.add(sid)

        # kind
        kind = str(_get(sp, "kind", "")).strip()
        if not kind:
            warnings.append("{}: отсутствует 'kind'".format(label))

        # rect
        rect = _as_py(_get(sp, "rect"))
        if not isinstance(rect, dict):
            errors.append("{}: отсутствует или некорректный 'rect'".format(label))
            continue

        x, y, w, h = _rect_from_space(sp)
        if x is None or y is None:
            errors.append("{}: rect не содержит корректные x_mm/y_mm".format(label))
        if w is None or not _is_positive(w):
            errors.append("{}: rect.width_mm должен быть > 0 (сейчас: {})".format(label, w))
        if h is None or not _is_positive(h):
            errors.append("{}: rect.length_mm должен быть > 0 (сейчас: {})".format(label, h))

        # height_mm
        height = _to_float(_get(sp, "height_mm"))
        if height is None or not _is_positive(height):
            warnings.append("{}: height_mm не задан или <= 0, будет использовано 3000".format(label))

        # boundary_mm
        boundary = _as_py(_get(sp, "boundary_mm"))
        if not isinstance(boundary, list) or len(boundary) < 3:
            warnings.append("{}: boundary_mm отсутствует или содержит < 3 точек".format(label))

        # center_mm
        center = _as_py(_get(sp, "center_mm"))
        if not isinstance(center, list) or len(center) < 2:
            warnings.append("{}: center_mm отсутствует или некорректный".format(label))


def validate_center_inside_rect(spaces, errors, warnings):
    """Проверяет, что center_mm каждого space лежит строго внутри его rect."""
    if not isinstance(spaces, list):
        return

    for i, sp in enumerate(spaces):
        sp = _as_py(sp)
        if not isinstance(sp, dict):
            continue

        sid = str(_get(sp, "id", "space_{}".format(i + 1)))
        x, y, w, h = _rect_from_space(sp)
        if x is None or y is None or w is None or h is None:
            continue
        if not _is_positive(w) or not _is_positive(h):
            continue

        center = _as_py(_get(sp, "center_mm"))
        if not isinstance(center, list) or len(center) < 2:
            continue

        cx = _to_float(center[0])
        cy = _to_float(center[1])
        if cx is None or cy is None:
            continue

        if not _point_inside_rect(cx, cy, x, y, w, h):
            errors.append(
                "Space '{}': center_mm [{}, {}] НЕ находится внутри rect "
                "(x={}, y={}, w={}, h={})".format(sid, cx, cy, x, y, w, h)
            )


def validate_no_overlaps(spaces, errors, warnings):
    """
    Проверяет, что помещения не пересекаются по площади.
    Касание границами (общая стена) — допустимо.
    """
    if not isinstance(spaces, list):
        return

    rects = []
    for i, sp in enumerate(spaces):
        sp = _as_py(sp)
        if not isinstance(sp, dict):
            continue
        sid = str(_get(sp, "id", "space_{}".format(i + 1)))
        x, y, w, h = _rect_from_space(sp)
        if x is None or y is None or w is None or h is None:
            continue
        if not _is_positive(w) or not _is_positive(h):
            continue
        rects.append((sid, x, y, w, h))

    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            sid_a, x1, y1, w1, h1 = rects[i]
            sid_b, x2, y2, w2, h2 = rects[j]

            if _rects_overlap(x1, y1, w1, h1, x2, y2, w2, h2):
                errors.append(
                    "Пересечение помещений: '{}' и '{}' "
                    "(rect A: x={}, y={}, w={}, h={} | "
                    "rect B: x={}, y={}, w={}, h={})".format(
                        sid_a, sid_b, x1, y1, w1, h1, x2, y2, w2, h2
                    )
                )


def validate_shared_boundaries(spaces, shared_boundaries, errors, warnings):
    """
    Проверяет, что каждая shared_boundary:
    1. Ссылается на существующие space ids
    2. Сегмент не нулевой длины
    3. Сегмент лежит на границе обоих пространств
    """
    if not isinstance(shared_boundaries, list):
        return

    space_map = {}
    if isinstance(spaces, list):
        for sp in spaces:
            sp = _as_py(sp)
            if isinstance(sp, dict):
                sid = str(_get(sp, "id", ""))
                if sid:
                    space_map[sid] = sp

    for i, sb in enumerate(shared_boundaries):
        sb = _as_py(sb)
        if not isinstance(sb, dict):
            warnings.append("shared_boundary #{} не является словарём".format(i + 1))
            continue

        a_id = str(_get(sb, "a", "")).strip()
        b_id = str(_get(sb, "b", "")).strip()
        segment = _as_py(_get(sb, "segment_mm"))

        label = "shared_boundary #{} ('{}' <-> '{}')".format(i + 1, a_id, b_id)

        # Проверка ссылок
        if not a_id or a_id not in space_map:
            errors.append("{}: space '{}' не найден".format(label, a_id))
        if not b_id or b_id not in space_map:
            errors.append("{}: space '{}' не найден".format(label, b_id))
        if a_id == b_id:
            errors.append("{}: ссылается на один и тот же space".format(label))

        # Проверка сегмента
        if not isinstance(segment, list) or len(segment) != 2:
            errors.append("{}: segment_mm должен содержать 2 точки".format(label))
            continue

        p1 = _as_py(segment[0])
        p2 = _as_py(segment[1])

        if not isinstance(p1, list) or len(p1) < 2 or not isinstance(p2, list) or len(p2) < 2:
            errors.append("{}: точки segment_mm некорректны".format(label))
            continue

        # Нулевой сегмент
        dx = _to_float(p1[0], 0) - _to_float(p2[0], 0)
        dy = _to_float(p1[1], 0) - _to_float(p2[1], 0)
        seg_len = (dx * dx + dy * dy) ** 0.5

        if seg_len < EPS:
            errors.append("{}: сегмент нулевой длины".format(label))
            continue

        # Проверка, что сегмент лежит на границе обоих space
        if a_id in space_map:
            sp_a = space_map[a_id]
            xa, ya, wa, ha = _rect_from_space(sp_a)
            if xa is not None and ya is not None and wa is not None and ha is not None:
                if not _segment_on_rect_edge(p1, p2, xa, ya, wa, ha):
                    warnings.append(
                        "{}: сегмент не лежит точно на границе space '{}'".format(label, a_id)
                    )

        if b_id in space_map:
            sp_b = space_map[b_id]
            xb, yb, wb, hb = _rect_from_space(sp_b)
            if xb is not None and yb is not None and wb is not None and hb is not None:
                if not _segment_on_rect_edge(p1, p2, xb, yb, wb, hb):
                    warnings.append(
                        "{}: сегмент не лежит точно на границе space '{}'".format(label, b_id)
                    )


def validate_bounding_box(spaces, bounding_box, errors, warnings):
    """Проверяет, что bounding_box охватывает все spaces."""
    if not isinstance(bounding_box, dict):
        warnings.append("bounding_box_mm отсутствует или не является словарём")
        return

    bb_min_x = _to_float(_get(bounding_box, "min_x_mm"), None)
    bb_min_y = _to_float(_get(bounding_box, "min_y_mm"), None)
    bb_max_x = _to_float(_get(bounding_box, "max_x_mm"), None)
    bb_max_y = _to_float(_get(bounding_box, "max_y_mm"), None)

    if bb_min_x is None or bb_min_y is None or bb_max_x is None or bb_max_y is None:
        warnings.append("bounding_box_mm содержит некорректные значения")
        return

    if bb_max_x <= bb_min_x or bb_max_y <= bb_min_y:
        errors.append(
            "bounding_box_mm: max <= min "
            "(min_x={}, max_x={}, min_y={}, max_y={})".format(
                bb_min_x, bb_max_x, bb_min_y, bb_max_y
            )
        )
        return

    if not isinstance(spaces, list):
        return

    for sp in spaces:
        sp = _as_py(sp)
        if not isinstance(sp, dict):
            continue

        sid = str(_get(sp, "id", ""))
        x, y, w, h = _rect_from_space(sp)
        if x is None or y is None or w is None or h is None:
            continue

        if x < bb_min_x - EPS or y < bb_min_y - EPS:
            errors.append(
                "Space '{}': начало rect ({}, {}) выходит за bounding_box "
                "(min_x={}, min_y={})".format(sid, x, y, bb_min_x, bb_min_y)
            )
        if x + w > bb_max_x + EPS or y + h > bb_max_y + EPS:
            errors.append(
                "Space '{}': конец rect ({}, {}) выходит за bounding_box "
                "(max_x={}, max_y={})".format(sid, x + w, y + h, bb_max_x, bb_max_y)
            )


def validate_layout_strategy(spaces, layout_strategy, errors, warnings):
    """Проверяет, что layout_strategy соответствует составу spaces."""
    if not isinstance(spaces, list) or not spaces:
        return

    corridors = []
    non_corridors = []

    for sp in spaces:
        sp = _as_py(sp)
        if not isinstance(sp, dict):
            continue
        kind = str(_get(sp, "kind", "")).strip().lower()
        if kind == "corridor":
            corridors.append(sp)
        else:
            non_corridors.append(sp)

    strategy = str(layout_strategy or "").strip().lower()

    if strategy == "single_room":
        if len(spaces) != 1:
            warnings.append(
                "layout_strategy='single_room', но spaces содержит {} элементов".format(len(spaces))
            )

    elif strategy == "corridor_with_rooms_one_side":
        if len(corridors) != 1:
            warnings.append(
                "layout_strategy='corridor_with_rooms_one_side', "
                "но найдено {} corridor-ов (ожидается 1)".format(len(corridors))
            )
        if not non_corridors:
            warnings.append(
                "layout_strategy='corridor_with_rooms_one_side', "
                "но нет помещений кроме коридора"
            )

    elif strategy == "row_of_rooms":
        if len(spaces) < 2:
            warnings.append(
                "layout_strategy='row_of_rooms', "
                "но spaces содержит {} элементов (ожидается >= 2)".format(len(spaces))
            )

    elif strategy:
        warnings.append("Неизвестная layout_strategy: '{}'".format(strategy))


def validate_relationships(relationships, space_ids, errors, warnings):
    """Проверяет, что relationships ссылаются на существующие space ids."""
    if not isinstance(relationships, list):
        return

    for i, rel in enumerate(relationships):
        rel = _as_py(rel)
        if not isinstance(rel, dict):
            warnings.append("relationship #{} не является словарём".format(i + 1))
            continue

        rtype = str(_get(rel, "type", "")).strip()
        rf = str(_get(rel, "from", "")).strip()
        rt = str(_get(rel, "to", "")).strip()

        if not rtype:
            warnings.append("relationship #{}: отсутствует 'type'".format(i + 1))
        if rf and rf not in space_ids:
            errors.append("relationship #{}: 'from' '{}' не найден в spaces".format(i + 1, rf))
        if rt and rt not in space_ids:
            errors.append("relationship #{}: 'to' '{}' не найден в spaces".format(i + 1, rt))
        if rf and rt and rf == rt:
            warnings.append("relationship #{}: 'from' и 'to' ссылаются на один space '{}'".format(i + 1, rf))


# =============================================
# ГЛАВНАЯ ЛОГИКА
# =============================================

try:
    raw_in = IN[0]
    node3a_out = _as_py(raw_in)

    if node3a_out is None:
        raise ValueError("IN[0] пуст. Подключи output Node 3A")

    if not isinstance(node3a_out, dict):
        raise ValueError(
            "IN[0] должен быть словарём из Node 3A. "
            "Сейчас: {}".format(str(type(node3a_out)))
        )

    # Проверяем что Node 3A вернул ok
    input_status = str(_get(node3a_out, "status", "")).strip().lower()
    if input_status != "ok":
        # Пробрасываем ошибку как есть
        OUT = {
            "status": "error",
            "error": "Node 3A вернул не-ok статус: " + str(node3a_out)[:1000],
            "source": "node3b_passthrough"
        }

    else:
        thought = str(_get(node3a_out, "thought", "") or "")
        topology = _as_py(_get(node3a_out, "topology", {}))
        layout_strategy = str(_get(node3a_out, "layout_strategy", "") or "")
        incoming_warnings = _as_py(_get(node3a_out, "warnings", []) or [])

        if not isinstance(incoming_warnings, list):
            incoming_warnings = []

        if not isinstance(topology, dict):
            raise ValueError("В Node 3A отсутствует корректное поле 'topology'")

        spaces = _as_py(_get(topology, "spaces", []))
        shared_boundaries = _as_py(_get(topology, "shared_boundaries", []))
        bounding_box = _as_py(_get(topology, "bounding_box_mm", {}))
        relationships = _as_py(_get(topology, "relationships", []))

        errors = []
        warnings = []

        # === 1. Структурная валидация spaces ===
        validate_spaces_structure(spaces, errors, warnings)

        # === 2. Center внутри rect ===
        validate_center_inside_rect(spaces, errors, warnings)

        # === 3. Нет пересечений между помещениями ===
        validate_no_overlaps(spaces, errors, warnings)

        # === 4. Shared boundaries корректны ===
        validate_shared_boundaries(spaces, shared_boundaries, errors, warnings)

        # === 5. Bounding box охватывает все spaces ===
        validate_bounding_box(spaces, bounding_box, errors, warnings)

        # === 6. Layout strategy соответствует составу ===
        validate_layout_strategy(spaces, layout_strategy, errors, warnings)

        # === 7. Relationships валидны ===
        space_ids = set()
        if isinstance(spaces, list):
            for sp in spaces:
                sp = _as_py(sp)
                if isinstance(sp, dict):
                    sid = str(_get(sp, "id", "")).strip()
                    if sid:
                        space_ids.add(sid)

        validate_relationships(relationships, space_ids, errors, warnings)

        # === Формируем выход ===
        all_warnings = incoming_warnings + warnings

        if errors:
            # БЛОКИРУЕМ — не пускаем в Node 4A
            OUT = {
                "status": "error",
                "error": "Topology validation failed",
                "thought": thought,
                "layout_strategy": layout_strategy,
                "topology": topology,
                "validation": {
                    "errors": errors,
                    "warnings": all_warnings,
                    "error_count": len(errors),
                    "warning_count": len(all_warnings)
                },
                "warnings": all_warnings
            }
        else:
            # ПРОПУСКАЕМ — формат совместим с тем, что ожидает Node 4A
            OUT = {
                "status": "ok",
                "thought": thought,
                "layout_strategy": layout_strategy,
                "topology": topology,
                "validation": {
                    "errors": [],
                    "warnings": all_warnings,
                    "error_count": 0,
                    "warning_count": len(all_warnings),
                    "validated": True
                },
                "warnings": all_warnings
            }

except Exception:
    OUT = {
        "status": "error",
        "error": "Критическая ошибка в Node 3B: " + traceback.format_exc()
    }
