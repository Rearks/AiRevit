# -*- coding: utf-8 -*-
# NODE 3A — Build Topology/Layout from Normalized Intent + soft timeout
# IN[0] : dict - Output from Node 2B
# IN[1] : number - timeout seconds (optional), default 600
# OUT   : dict - {"status", "thought", "layout_strategy", "topology", "warnings"}

import copy
import time
import traceback

OUT = {"status": "Node 3A: не запущен"}
DEADLINE = None

try:
    string_types = (basestring,)
except:
    string_types = (str,)

# =============================================
# TIMEOUT
# =============================================

def _set_timeout(seconds):
    global DEADLINE
    if seconds is None:
        seconds = 600.0
    try:
        seconds = float(seconds)
    except:
        seconds = 600.0
    if seconds <= 0:
        seconds = 600.0
    DEADLINE = time.time() + seconds
    return seconds

def _check_timeout(step=""):
    global DEADLINE
    if DEADLINE is None:
        return
    if time.time() > DEADLINE:
        raise Exception("TIMEOUT: Node 3A превысил лимит времени на шаге '{}'".format(step))

# =============================================
# УТИЛИТЫ
# =============================================

def _is_string(x):
    return isinstance(x, string_types)

def _as_py(obj):
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

    if hasattr(obj, "Keys") and hasattr(obj, "__getitem__"):
        try:
            d = {}
            for k in obj.Keys:
                d[str(k)] = _as_py(obj[k])
            return d
        except:
            pass

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

def _copy_dict(x):
    try:
        return copy.deepcopy(x)
    except:
        try:
            return dict(x)
        except:
            return {}

def _rect(x, y, w, h):
    return {
        "x_mm": float(x),
        "y_mm": float(y),
        "width_mm": float(w),
        "length_mm": float(h)
    }

def _rect_boundary_mm(r):
    _check_timeout("rect_boundary")
    x = _to_float(_get(r, "x_mm", 0), 0)
    y = _to_float(_get(r, "y_mm", 0), 0)
    w = _to_float(_get(r, "width_mm", 0), 0)
    h = _to_float(_get(r, "length_mm", 0), 0)
    return [
        [x, y],
        [x + w, y],
        [x + w, y + h],
        [x, y + h]
    ]

def _rect_center_mm(r):
    _check_timeout("rect_center")
    x = _to_float(_get(r, "x_mm", 0), 0)
    y = _to_float(_get(r, "y_mm", 0), 0)
    w = _to_float(_get(r, "width_mm", 0), 0)
    h = _to_float(_get(r, "length_mm", 0), 0)
    return [x + w / 2.0, y + h / 2.0, 0.0]

def _bbox_from_rects(rects):
    _check_timeout("bbox_start")

    if not rects:
        return {
            "min_x_mm": 0.0,
            "min_y_mm": 0.0,
            "max_x_mm": 0.0,
            "max_y_mm": 0.0
        }

    min_x = None
    min_y = None
    max_x = None
    max_y = None

    for r in rects:
        _check_timeout("bbox_loop")
        x = _to_float(_get(r, "x_mm", 0), 0)
        y = _to_float(_get(r, "y_mm", 0), 0)
        w = _to_float(_get(r, "width_mm", 0), 0)
        h = _to_float(_get(r, "length_mm", 0), 0)

        rx2 = x + w
        ry2 = y + h

        if min_x is None or x < min_x:
            min_x = x
        if min_y is None or y < min_y:
            min_y = y
        if max_x is None or rx2 > max_x:
            max_x = rx2
        if max_y is None or ry2 > max_y:
            max_y = ry2

    return {
        "min_x_mm": float(min_x),
        "min_y_mm": float(min_y),
        "max_x_mm": float(max_x),
        "max_y_mm": float(max_y)
    }

def _bbox_boundary_mm(b):
    _check_timeout("bbox_boundary")
    min_x = _to_float(_get(b, "min_x_mm", 0), 0)
    min_y = _to_float(_get(b, "min_y_mm", 0), 0)
    max_x = _to_float(_get(b, "max_x_mm", 0), 0)
    max_y = _to_float(_get(b, "max_y_mm", 0), 0)

    return [
        [min_x, min_y],
        [max_x, min_y],
        [max_x, max_y],
        [min_x, max_y]
    ]

def _make_shared_boundary(space_a_id, space_b_id, p1, p2, orientation):
    _check_timeout("shared_boundary")
    return {
        "a": str(space_a_id),
        "b": str(space_b_id),
        "segment_mm": [
            [float(p1[0]), float(p1[1])],
            [float(p2[0]), float(p2[1])]
        ],
        "orientation": str(orientation)
    }

def _enrich_space_with_geometry(space_dict, rect_dict):
    _check_timeout("enrich_space")
    sp = _copy_dict(space_dict)
    sp["rect"] = rect_dict
    sp["boundary_mm"] = _rect_boundary_mm(rect_dict)
    sp["center_mm"] = _rect_center_mm(rect_dict)
    return sp

def _require_space_dims(sp, allow_missing_length_for_corridor=False):
    _check_timeout("require_space_dims")

    sid = str(_get(sp, "id", "unknown"))
    kind = str(_get(sp, "kind", "room")).strip().lower()

    width_mm = _to_float(_get(sp, "width_mm"))
    length_mm = _to_float(_get(sp, "length_mm"))
    height_mm = _to_float(_get(sp, "height_mm"), 3000.0)

    if not _is_positive(width_mm):
        raise ValueError("Space '{}' должен иметь положительный width_mm".format(sid))

    if kind == "corridor" and allow_missing_length_for_corridor:
        if length_mm is not None and not _is_positive(length_mm):
            length_mm = None
    else:
        if not _is_positive(length_mm):
            raise ValueError("Space '{}' должен иметь положительный length_mm".format(sid))

    if not _is_positive(height_mm):
        height_mm = 3000.0

    return width_mm, length_mm, height_mm

# =============================================
# СТРАТЕГИИ РАСКЛАДКИ
# =============================================

def _layout_single_room(spaces, warnings):
    _check_timeout("layout_single_room")

    if len(spaces) != 1:
        raise ValueError("single_room ожидает ровно один space")

    sp = _copy_dict(spaces[0])
    width_mm, length_mm, height_mm = _require_space_dims(sp, False)

    rect = _rect(0.0, 0.0, width_mm, length_mm)
    placed = [_enrich_space_with_geometry(sp, rect)]

    bbox = _bbox_from_rects([rect])

    return {
        "version": "1.0",
        "layout_strategy": "single_room",
        "spaces": placed,
        "shared_boundaries": [],
        "bounding_box_mm": bbox,
        "bounding_boundary_mm": _bbox_boundary_mm(bbox)
    }

def _layout_row_of_rooms(spaces, warnings):
    _check_timeout("layout_row_of_rooms_start")

    if not spaces:
        raise ValueError("row_of_rooms: spaces пуст")

    placed = []
    shared_boundaries = []
    x_cursor = 0.0
    prev_space = None
    rects = []

    for sp in spaces:
        _check_timeout("layout_row_of_rooms_loop")

        sp_copy = _copy_dict(sp)
        width_mm, length_mm, height_mm = _require_space_dims(sp_copy, False)

        rect = _rect(x_cursor, 0.0, width_mm, length_mm)
        rects.append(rect)
        current = _enrich_space_with_geometry(sp_copy, rect)
        placed.append(current)

        if prev_space is not None:
            prev_rect = _get(prev_space, "rect", {})
            curr_rect = rect

            x_shared = _to_float(_get(curr_rect, "x_mm", 0), 0)
            y1 = 0.0
            y2 = min(
                _to_float(_get(prev_rect, "length_mm", 0), 0),
                _to_float(_get(curr_rect, "length_mm", 0), 0)
            )

            if y2 > y1:
                shared_boundaries.append(
                    _make_shared_boundary(
                        _get(prev_space, "id", ""),
                        _get(current, "id", ""),
                        [x_shared, y1],
                        [x_shared, y2],
                        "vertical"
                    )
                )

        prev_space = current
        x_cursor += width_mm

    bbox = _bbox_from_rects(rects)

    return {
        "version": "1.0",
        "layout_strategy": "row_of_rooms",
        "spaces": placed,
        "shared_boundaries": shared_boundaries,
        "bounding_box_mm": bbox,
        "bounding_boundary_mm": _bbox_boundary_mm(bbox)
    }

def _layout_corridor_with_rooms_one_side(spaces, warnings):
    _check_timeout("layout_corridor_start")

    corridors = []
    rooms = []

    for sp in spaces:
        _check_timeout("layout_corridor_split")
        kind = str(_get(sp, "kind", "")).strip().lower()
        if kind == "corridor":
            corridors.append(sp)
        else:
            rooms.append(sp)

    if len(corridors) != 1:
        raise ValueError("corridor_with_rooms_one_side ожидает ровно один corridor")
    if not rooms:
        raise ValueError("corridor_with_rooms_one_side требует хотя бы один room space")

    corridor = _copy_dict(corridors[0])

    corr_width_mm, corr_length_mm, corr_height_mm = _require_space_dims(
        corridor,
        True
    )

    room_width_sum = 0.0
    cleaned_rooms = []

    for sp in rooms:
        _check_timeout("layout_corridor_rooms_prepare")
        sp_copy = _copy_dict(sp)
        width_mm, length_mm, height_mm = _require_space_dims(sp_copy, False)
        room_width_sum += width_mm
        cleaned_rooms.append(sp_copy)

    final_corr_length = room_width_sum

    if _is_positive(corr_length_mm):
        if corr_length_mm < room_width_sum:
            warnings.append(
                "Длина corridor меньше суммарной ширины комнат. Corridor length переопределён: {} -> {}".format(
                    corr_length_mm, room_width_sum
                )
            )
            final_corr_length = room_width_sum
        else:
            final_corr_length = corr_length_mm
            if corr_length_mm > room_width_sum:
                warnings.append("Corridor длиннее фронта комнат. Останется свободный участок corridor.")

    corridor_rect = _rect(0.0, 0.0, final_corr_length, corr_width_mm)
    placed = [_enrich_space_with_geometry(corridor, corridor_rect)]
    rects = [corridor_rect]
    shared_boundaries = []

    x_cursor = 0.0
    prev_room = None

    for sp in cleaned_rooms:
        _check_timeout("layout_corridor_rooms_loop")

        room_w = _to_float(_get(sp, "width_mm", 0), 0)
        room_l = _to_float(_get(sp, "length_mm", 0), 0)

        room_rect = _rect(x_cursor, corr_width_mm, room_w, room_l)
        room_geo = _enrich_space_with_geometry(sp, room_rect)

        placed.append(room_geo)
        rects.append(room_rect)

        shared_boundaries.append(
            _make_shared_boundary(
                _get(room_geo, "id", ""),
                _get(corridor, "id", ""),
                [x_cursor, corr_width_mm],
                [x_cursor + room_w, corr_width_mm],
                "horizontal"
            )
        )

        if prev_room is not None:
            prev_rect = _get(prev_room, "rect", {})
            curr_rect = room_rect

            x_shared = _to_float(_get(curr_rect, "x_mm", 0), 0)
            y1 = corr_width_mm
            y2 = corr_width_mm + min(
                _to_float(_get(prev_rect, "length_mm", 0), 0),
                _to_float(_get(curr_rect, "length_mm", 0), 0)
            )

            if y2 > y1:
                shared_boundaries.append(
                    _make_shared_boundary(
                        _get(prev_room, "id", ""),
                        _get(room_geo, "id", ""),
                        [x_shared, y1],
                        [x_shared, y2],
                        "vertical"
                    )
                )

        prev_room = room_geo
        x_cursor += room_w

    bbox = _bbox_from_rects(rects)

    return {
        "version": "1.0",
        "layout_strategy": "corridor_with_rooms_one_side",
        "spaces": placed,
        "shared_boundaries": shared_boundaries,
        "bounding_box_mm": bbox,
        "bounding_boundary_mm": _bbox_boundary_mm(bbox)
    }

def _choose_layout_strategy(spaces, relationships, warnings):
    _check_timeout("choose_layout_strategy")

    if not spaces:
        raise ValueError("spaces пуст")

    corridors = [sp for sp in spaces if str(_get(sp, "kind", "")).strip().lower() == "corridor"]
    non_corridors = [sp for sp in spaces if str(_get(sp, "kind", "")).strip().lower() != "corridor"]

    if relationships:
        warnings.append("Relationships сохранены, но в Node 3A v1 пока не влияют на layout_strategy")

    if len(spaces) == 1:
        return "single_room"

    if len(corridors) == 1 and len(non_corridors) >= 1:
        return "corridor_with_rooms_one_side"

    if len(corridors) > 1:
        warnings.append("Несколько corridor пока не поддерживаются. Используется fallback 'row_of_rooms'.")

    return "row_of_rooms"

# =============================================
# ГЛАВНАЯ ЛОГИКА
# =============================================

try:
    timeout_input = None
    try:
        timeout_input = IN[1]
    except:
        timeout_input = 600

    timeout_sec = _set_timeout(timeout_input)

    raw_in = IN[0]
    node2b_out = _as_py(raw_in)
    _check_timeout("input_read")

    if node2b_out is None:
        raise ValueError("IN[0] пуст. Подключи output Node 2B")

    # Если случайно подключили Node 2A
    if isinstance(node2b_out, (list, tuple)):
        raise ValueError(
            "В Node 3A подан список, похожий на output Node 2A. "
            "Подключи именно Node 2B -> Node 3A."
        )

    if not isinstance(node2b_out, dict):
        raise ValueError("IN[0] должен быть словарём из Node 2B. Сейчас: {}".format(str(type(node2b_out))))

    status = str(_get(node2b_out, "status", "")).strip().lower()
    if status != "ok":
        raise ValueError("Node 2B вернул не-ok статус: " + str(node2b_out)[:1000])

    thought = str(_get(node2b_out, "thought", "") or "")
    intent = _as_py(_get(node2b_out, "intent", {}))
    warnings = _as_py(_get(node2b_out, "warnings", []) or [])
    if not isinstance(warnings, list):
        warnings = []

    if not isinstance(intent, dict):
        raise ValueError("Поле 'intent' в Node 2B должно быть словарём")

    spaces = _as_py(_get(intent, "spaces", []))
    relationships = _as_py(_get(intent, "relationships", []))
    project_scope = _as_py(_get(intent, "project_scope", {}))
    preferences = _as_py(_get(intent, "preferences", {}))
    constraints = _as_py(_get(intent, "constraints", {}))

    if not isinstance(spaces, list) or not spaces:
        raise ValueError("Intent не содержит spaces")

    if not isinstance(relationships, list):
        relationships = []

    _check_timeout("before_strategy")
    layout_strategy = _choose_layout_strategy(spaces, relationships, warnings)

    _check_timeout("before_layout_build")
    if layout_strategy == "single_room":
        topology_core = _layout_single_room(spaces, warnings)
    elif layout_strategy == "corridor_with_rooms_one_side":
        topology_core = _layout_corridor_with_rooms_one_side(spaces, warnings)
    else:
        topology_core = _layout_row_of_rooms(spaces, warnings)

    _check_timeout("before_topology_output")
    topology = {
        "version": "1.0",
        "project_scope": _copy_dict(project_scope),
        "preferences": _copy_dict(preferences),
        "constraints": _copy_dict(constraints),
        "relationships": copy.deepcopy(relationships),
        "layout_strategy": layout_strategy,
        "spaces": _get(topology_core, "spaces", []),
        "shared_boundaries": _get(topology_core, "shared_boundaries", []),
        "bounding_box_mm": _get(topology_core, "bounding_box_mm", {}),
        "bounding_boundary_mm": _get(topology_core, "bounding_boundary_mm", [])
    }

    OUT = {
        "status": "ok",
        "thought": thought,
        "layout_strategy": layout_strategy,
        "timeout_sec": timeout_sec,
        "topology": topology,
        "warnings": warnings
    }

except Exception as e:
    msg = str(e)
    if msg.startswith("TIMEOUT:"):
        OUT = {
            "status": "timeout",
            "error": msg
        }
    else:
        OUT = {
            "status": "error",
            "error": "Критическая ошибка в Node 3A: " + traceback.format_exc()
        }
