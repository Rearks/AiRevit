# -*- coding: utf-8 -*-
# NODE 4A — Compile Topology to Revit Action Plan
# IN[0] : dict - Output from Node 3A
# OUT   : list - [thought, actions_list, status, meta]
#
# Совместим со старым Executor (старый Node 3), который ожидает:
# [thought, actions_list, status]

import copy
import traceback

OUT = ["Node 4A: не запущен", [], ""]

try:
    string_types = (basestring,)
except:
    string_types = (str,)

EPS = 1e-6

# =============================================
# UTILS
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

def _n(v):
    """Нормализация числа для ключей словаря."""
    try:
        return round(float(v), 6)
    except:
        return 0.0

def _rect_data(space):
    rect = _as_py(_get(space, "rect", {}))
    if not isinstance(rect, dict):
        rect = {}

    x = _to_float(_get(rect, "x_mm", 0), 0.0)
    y = _to_float(_get(rect, "y_mm", 0), 0.0)
    w = _to_float(_get(rect, "width_mm", 0), 0.0)
    l = _to_float(_get(rect, "length_mm", 0), 0.0)

    return x, y, w, l

def _add_breakpoint(breaks_dict, coord, val1, val2):
    c = _n(coord)
    if c not in breaks_dict:
        breaks_dict[c] = set()
    breaks_dict[c].add(_n(val1))
    breaks_dict[c].add(_n(val2))

def _make_edge(orientation, coord, a1, a2, owner_id, height_mm):
    return {
        "orientation": orientation,   # "H" or "V"
        "coord": _n(coord),
        "a1": _n(min(a1, a2)),
        "a2": _n(max(a1, a2)),
        "owner_id": str(owner_id),
        "height_mm": _to_float(height_mm, 3000.0)
    }

def _edge_sort_key(seg):
    ori = _get(seg, "orientation", "")
    coord = _to_float(_get(seg, "coord", 0), 0)
    a1 = _to_float(_get(seg, "a1", 0), 0)
    a2 = _to_float(_get(seg, "a2", 0), 0)
    ori_rank = 0 if ori == "H" else 1
    return (ori_rank, coord, a1, a2)

# =============================================
# BUILD EDGES FROM SPACES
# =============================================

def _collect_space_edges(spaces, warnings):
    edges = []
    vertical_breaks = {}
    horizontal_breaks = {}

    for i, sp in enumerate(spaces):
        sp = _as_py(sp)
        if not isinstance(sp, dict):
            continue

        sid = str(_get(sp, "id", "space_{}".format(i + 1)))
        height_mm = _to_float(_get(sp, "height_mm", 3000), 3000.0)

        x, y, w, l = _rect_data(sp)

        if not _is_positive(w) or not _is_positive(l):
            raise ValueError("Space '{}' имеет неположительные размеры rect".format(sid))

        x1 = x
        y1 = y
        x2 = x + w
        y2 = y + l

        # 4 границы прямоугольника
        # bottom
        edges.append(_make_edge("H", y1, x1, x2, sid, height_mm))
        _add_breakpoint(horizontal_breaks, y1, x1, x2)

        # top
        edges.append(_make_edge("H", y2, x1, x2, sid, height_mm))
        _add_breakpoint(horizontal_breaks, y2, x1, x2)

        # left
        edges.append(_make_edge("V", x1, y1, y2, sid, height_mm))
        _add_breakpoint(vertical_breaks, x1, y1, y2)

        # right
        edges.append(_make_edge("V", x2, y1, y2, sid, height_mm))
        _add_breakpoint(vertical_breaks, x2, y1, y2)

    return edges, vertical_breaks, horizontal_breaks

# =============================================
# SPLIT EDGES TO PRIMITIVE UNIQUE SEGMENTS
# =============================================

def _split_edges_to_unique_segments(edges, vertical_breaks, horizontal_breaks):
    segment_map = {}

    for e in edges:
        orientation = _get(e, "orientation", "")
        coord = _n(_get(e, "coord", 0))
        a1 = _n(_get(e, "a1", 0))
        a2 = _n(_get(e, "a2", 0))
        owner_id = str(_get(e, "owner_id", ""))
        height_mm = _to_float(_get(e, "height_mm", 3000), 3000.0)

        if orientation == "H":
            pts = sorted(list(horizontal_breaks.get(coord, set())))
        else:
            pts = sorted(list(vertical_breaks.get(coord, set())))

        # Оставляем только точки внутри диапазона ребра
        relevant = []
        for p in pts:
            if p >= a1 - EPS and p <= a2 + EPS:
                relevant.append(_n(p))

        # гарантируем концы
        if a1 not in relevant:
            relevant.append(a1)
        if a2 not in relevant:
            relevant.append(a2)

        relevant = sorted(list(set(relevant)))

        for i in range(len(relevant) - 1):
            s = _n(relevant[i])
            t = _n(relevant[i + 1])

            if t - s <= EPS:
                continue

            if s < a1 - EPS or t > a2 + EPS:
                continue

            key = (orientation, coord, s, t)

            if key not in segment_map:
                segment_map[key] = {
                    "orientation": orientation,
                    "coord": coord,
                    "a1": s,
                    "a2": t,
                    "owners": [],
                    "heights": []
                }

            segment_map[key]["owners"].append(owner_id)
            segment_map[key]["heights"].append(height_mm)

    return segment_map

# =============================================
# ACTION BUILDERS
# =============================================

def _build_wall_actions(segment_map, level_keyword, wall_type_keyword):
    actions = []
    unique_segments = []

    for key in sorted(segment_map.keys(), key=lambda k: (0 if k[0] == "H" else 1, k[1], k[2], k[3])):
        seg = segment_map[key]
        unique_segments.append(seg)

        orientation = seg["orientation"]
        coord = _to_float(seg["coord"], 0.0)
        a1 = _to_float(seg["a1"], 0.0)
        a2 = _to_float(seg["a2"], 0.0)
        heights = seg.get("heights", [])
        height_mm = max([_to_float(h, 3000.0) for h in heights]) if heights else 3000.0

        if orientation == "H":
            start_mm = [a1, coord, 0.0]
            end_mm   = [a2, coord, 0.0]
        else:
            start_mm = [coord, a1, 0.0]
            end_mm   = [coord, a2, 0.0]

        actions.append({
            "action": "create_wall",
            "params": {
                "level_keyword": level_keyword,
                "wall_type_keyword": wall_type_keyword,
                "start_mm": start_mm,
                "end_mm": end_mm,
                "height_mm": height_mm
            }
        })

    return actions, unique_segments

def _build_floor_actions(spaces, level_keyword, floor_type_keyword):
    actions = []

    for sp in spaces:
        sp = _as_py(sp)
        if not isinstance(sp, dict):
            continue

        rect = _as_py(_get(sp, "rect", {}))
        sid = str(_get(sp, "id", ""))
        x = _to_float(_get(rect, "x_mm", 0), 0.0)
        y = _to_float(_get(rect, "y_mm", 0), 0.0)
        w = _to_float(_get(rect, "width_mm", 0), 0.0)   # X size
        l = _to_float(_get(rect, "length_mm", 0), 0.0)  # Y size

        if not _is_positive(w) or not _is_positive(l):
            raise ValueError("Space '{}' не может создать floor: неположительный rect".format(sid))

        actions.append({
            "action": "create_floor",
            "params": {
                "level_keyword": level_keyword,
                "floor_type_keyword": floor_type_keyword,
                "origin_mm": [x, y, 0.0],
                "length_mm": w,
                "width_mm": l
            }
        })

    return actions

def _build_room_actions(spaces, level_keyword):
    actions = []

    for sp in spaces:
        sp = _as_py(sp)
        if not isinstance(sp, dict):
            continue

        sid = str(_get(sp, "id", ""))
        name = str(_get(sp, "name", sid))
        room_number = str(_get(sp, "room_number", ""))
        center = _as_py(_get(sp, "center_mm", [0, 0, 0]))

        if not isinstance(center, list) or len(center) < 2:
            x, y, w, l = _rect_data(sp)
            center = [x + w / 2.0, y + l / 2.0, 0.0]

        if len(center) == 2:
            center = [center[0], center[1], 0.0]

        actions.append({
            "action": "create_room",
            "params": {
                "level_keyword": level_keyword,
                "center_mm": center,
                "room_number": room_number,
                "room_name": name
            }
        })

    return actions

# =============================================
# MAIN
# =============================================

try:
    node3a_out = _as_py(IN[0])

    if node3a_out is None:
        OUT = ["ERROR", [], "Node 4A: IN[0] пуст"]
    elif not isinstance(node3a_out, dict):
        OUT = ["ERROR", [], "Node 4A: IN[0] должен быть словарём из Node 3A"]
    else:
        status = str(_get(node3a_out, "status", "")).strip().lower()

        if status != "ok":
            OUT = ["ERROR", [], "Node 3A вернул не-ok статус: " + str(node3a_out)[:800]]
        else:
            thought = str(_get(node3a_out, "thought", "") or "")
            topology = _as_py(_get(node3a_out, "topology", {}))
            warnings = _as_py(_get(node3a_out, "warnings", []) or [])

            if not isinstance(warnings, list):
                warnings = []

            if not isinstance(topology, dict):
                raise ValueError("В Node 3A нет корректного поля 'topology'")

            project_scope = _as_py(_get(topology, "project_scope", {}))
            preferences = _as_py(_get(topology, "preferences", {}))
            spaces = _as_py(_get(topology, "spaces", []))

            if not isinstance(project_scope, dict):
                project_scope = {}
            if not isinstance(preferences, dict):
                preferences = {}
            if not isinstance(spaces, list) or not spaces:
                raise ValueError("Topology не содержит spaces")

            level_keyword = str(_get(project_scope, "level_keyword", "") or "").strip()
            wall_type_keyword = str(_get(preferences, "wall_type_keyword", "") or "").strip()
            floor_type_keyword = str(_get(preferences, "floor_type_keyword", "") or "").strip()

            # 1. Собираем рёбра помещений
            edges, vertical_breaks, horizontal_breaks = _collect_space_edges(spaces, warnings)

            # 2. Разбиваем в уникальные сегменты стен
            segment_map = _split_edges_to_unique_segments(edges, vertical_breaks, horizontal_breaks)

            # 3. Строим actions
            wall_actions, unique_segments = _build_wall_actions(segment_map, level_keyword, wall_type_keyword)
            floor_actions = _build_floor_actions(spaces, level_keyword, floor_type_keyword)
            room_actions = _build_room_actions(spaces, level_keyword)

            actions = []
            actions.extend(wall_actions)
            actions.extend(floor_actions)
            actions.extend(room_actions)

            meta = {
                "layout_strategy": str(_get(node3a_out, "layout_strategy", "")),
                "space_count": len(spaces),
                "edge_count_raw": len(edges),
                "wall_segment_count_unique": len(unique_segments),
                "wall_action_count": len(wall_actions),
                "floor_action_count": len(floor_actions),
                "room_action_count": len(room_actions),
                "warnings": warnings
            }

            OUT = [thought, actions, "OK", meta]

except Exception:
    OUT = ["ERROR", [], "Критическая ошибка в Node 4A: " + traceback.format_exc()]
