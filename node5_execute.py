# -*- coding: utf-8 -*-
# NODE 5 — Execute Compiled BIM Action Plan in Revit
#
# IN[0] : list/dict - output from Node 4A
#         usually [thought, actions_list, status, meta]
# IN[1] : bool - strict_mode (optional), default False
# IN[2] : number - timeout seconds (optional), default 600
#
# OUT   : dict
# {
#   "status": "success/partial/error/timeout",
#   "thought": "...",
#   "meta": {...},
#   "results": [...],
#   "summary": {...}
# }

import traceback
import time

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import *

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

try:
    from System.Collections.Generic import List as NetList
except:
    NetList = None

OUT = {"status": "Node 5: не запущен"}

MM = 1.0 / 304.8  # мм -> футы
DEADLINE = None

try:
    string_types = (basestring,)
except:
    string_types = (str,)

# =========================================================
# TIMEOUT
# =========================================================

def _set_timeout(seconds):
    global DEADLINE
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
        raise Exception("TIMEOUT: Node 5 превысил лимит времени на шаге '{}'".format(step))

# =========================================================
# PY / .NET HELPERS
# =========================================================

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

def _to_bool(v, d=False):
    try:
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        if s in ["true", "1", "yes", "y"]:
            return True
        if s in ["false", "0", "no", "n"]:
            return False
        return d
    except:
        return d

def _elem_name(x):
    try:
        return str(Element.Name.GetValue(x) or "")
    except:
        pass
    try:
        return str(x.Name or "")
    except:
        pass
    return ""

# =========================================================
# REVIT LOOKUP HELPERS
# =========================================================

def _collect_sorted(doc, cls):
    items = list(FilteredElementCollector(doc).OfClass(cls))
    items.sort(key=lambda x: _elem_name(x).lower())
    return items

def _find_best(doc, cls, keyword="", fallback_first=True):
    items = _collect_sorted(doc, cls)
    if not items:
        return None, "not_found"

    kw = str(keyword or "").strip().lower()
    if not kw:
        return (items[0] if fallback_first else None), "fallback_first"

    # 1. exact
    exact = [x for x in items if _elem_name(x).strip().lower() == kw]
    if exact:
        return exact[0], "exact"

    # 2. startswith
    starts = [x for x in items if _elem_name(x).strip().lower().startswith(kw)]
    if starts:
        return starts[0], "startswith"

    # 3. contains
    contains = [x for x in items if kw in _elem_name(x).lower()]
    if contains:
        return contains[0], "contains"

    return (items[0] if fallback_first else None), "fallback_first"

def _pt(arr_mm):
    arr_mm = _as_py(arr_mm)
    if not isinstance(arr_mm, list):
        arr_mm = [0, 0, 0]

    x = _to_float(arr_mm[0], 0.0) if len(arr_mm) > 0 else 0.0
    y = _to_float(arr_mm[1], 0.0) if len(arr_mm) > 1 else 0.0
    z = _to_float(arr_mm[2], 0.0) if len(arr_mm) > 2 else 0.0
    return XYZ(x * MM, y * MM, z * MM)

def _uv(arr_mm):
    arr_mm = _as_py(arr_mm)
    if not isinstance(arr_mm, list):
        arr_mm = [0, 0, 0]

    x = _to_float(arr_mm[0], 0.0) if len(arr_mm) > 0 else 0.0
    y = _to_float(arr_mm[1], 0.0) if len(arr_mm) > 1 else 0.0
    return UV(x * MM, y * MM)

def _set_param_str(el, bip, value):
    if value is None or value == "":
        return
    try:
        p = el.get_Parameter(bip)
        if p and not p.IsReadOnly:
            p.Set(str(value))
    except:
        pass

def _set_param_int(el, bip, value):
    try:
        p = el.get_Parameter(bip)
        if p and not p.IsReadOnly:
            p.Set(int(value))
    except:
        pass

# =========================================================
# FLOOR HELPERS
# =========================================================

def _build_closed_curves_from_boundary_mm(boundary_mm):
    boundary_mm = _as_py(boundary_mm)
    if not isinstance(boundary_mm, list) or len(boundary_mm) < 3:
        raise ValueError("boundary_mm должен содержать минимум 3 точки")

    pts = []
    for p in boundary_mm:
        p = _as_py(p)
        if not isinstance(p, list) or len(p) < 2:
            raise ValueError("Каждая точка boundary_mm должна быть [x,y] или [x,y,z]")
        x = _to_float(p[0], None)
        y = _to_float(p[1], None)
        z = _to_float(p[2], 0.0) if len(p) > 2 else 0.0
        if x is None or y is None:
            raise ValueError("Некорректная точка boundary_mm: {}".format(str(p)))
        pts.append(XYZ(x * MM, y * MM, z * MM))

    curves = []
    n = len(pts)
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        if a.DistanceTo(b) <= 1e-9:
            raise ValueError("В boundary_mm есть совпадающие соседние точки")
        curves.append(Line.CreateBound(a, b))

    return curves

def _build_rect_curves_from_origin(origin_mm, length_mm, width_mm):
    origin_mm = _as_py(origin_mm)
    if not isinstance(origin_mm, list):
        origin_mm = [0, 0, 0]

    x0 = _to_float(origin_mm[0], 0.0) if len(origin_mm) > 0 else 0.0
    y0 = _to_float(origin_mm[1], 0.0) if len(origin_mm) > 1 else 0.0
    z0 = _to_float(origin_mm[2], 0.0) if len(origin_mm) > 2 else 0.0

    L = _to_float(length_mm, None)
    W = _to_float(width_mm, None)

    if L is None or L <= 0:
        raise ValueError("length_mm должен быть > 0")
    if W is None or W <= 0:
        raise ValueError("width_mm должен быть > 0")

    p1 = XYZ(x0 * MM,       y0 * MM,       z0 * MM)
    p2 = XYZ((x0+L) * MM,   y0 * MM,       z0 * MM)
    p3 = XYZ((x0+L) * MM,   (y0+W) * MM,   z0 * MM)
    p4 = XYZ(x0 * MM,       (y0+W) * MM,   z0 * MM)

    return [
        Line.CreateBound(p1, p2),
        Line.CreateBound(p2, p3),
        Line.CreateBound(p3, p4),
        Line.CreateBound(p4, p1)
    ]

def _create_floor_compat(doc, curves, floor_type, level):
    if not curves or len(curves) < 3:
        raise ValueError("Недостаточно кривых для пола")

    # New API
    if hasattr(Floor, "Create"):
        try:
            loop = CurveLoop()
            for c in curves:
                loop.Append(c)

            loops = NetList[CurveLoop]() if NetList else []
            loops.Add(loop)
            return Floor.Create(doc, loops, floor_type.Id, level.Id)
        except Exception as e_new:
            # Old API fallback
            try:
                ca = CurveArray()
                for c in curves:
                    ca.Append(c)
                return doc.Create.NewFloor(ca, floor_type, level, False)
            except Exception as e_old:
                raise Exception("Floor.Create failed: {} | NewFloor failed: {}".format(e_new, e_old))
    else:
        ca = CurveArray()
        for c in curves:
            ca.Append(c)
        return doc.Create.NewFloor(ca, floor_type, level, False)

# =========================================================
# PLAN INPUT
# =========================================================

def _parse_plan_input(raw):
    raw = _as_py(raw)

    # Case 1: output from Node 4A
    if isinstance(raw, list) and len(raw) >= 3:
        thought = str(raw[0])
        actions = _as_py(raw[1])
        status = str(raw[2])
        meta = _as_py(raw[3]) if len(raw) > 3 else {}
        return thought, actions, status, meta

    # Case 2: dict-style future format
    if isinstance(raw, dict):
        thought = str(_get(raw, "thought", ""))
        actions = _as_py(_get(raw, "actions", []))
        status = str(_get(raw, "status", ""))
        meta = _as_py(_get(raw, "meta", {}))
        return thought, actions, status, meta

    raise ValueError("IN[0] должен быть output из Node 4A")

# =========================================================
# ACTION PRIMITIVES
# =========================================================

def prim_create_wall(doc, p):
    _check_timeout("prim_create_wall")

    p = _as_py(p)
    if not isinstance(p, dict):
        return {"ok": False, "error": "params для create_wall не являются словарём"}

    level_keyword = str(_get(p, "level_keyword", "") or "")
    wall_type_keyword = str(_get(p, "wall_type_keyword", "") or "")

    level, level_match = _find_best(doc, Level, level_keyword, True)
    wall_type, wt_match = _find_best(doc, WallType, wall_type_keyword, True)

    if not level:
        return {"ok": False, "error": "Level не найден"}
    if not wall_type:
        return {"ok": False, "error": "WallType не найден"}

    start = _pt(_get(p, "start_mm", [0, 0, 0]))
    end   = _pt(_get(p, "end_mm", [1000, 0, 0]))
    h_mm  = _to_float(_get(p, "height_mm", 3000), 3000.0)

    if h_mm <= 0:
        return {"ok": False, "error": "height_mm должен быть > 0"}
    if start.DistanceTo(end) <= 1e-9:
        return {"ok": False, "error": "Стена нулевой длины"}

    line = Line.CreateBound(start, end)
    wall = Wall.Create(doc, line, wall_type.Id, level.Id, h_mm * MM, 0.0, False, False)

    # Пытаемся явно включить room bounding
    try:
        p_rb = wall.get_Parameter(BuiltInParameter.WALL_ATTR_ROOM_BOUNDING)
        if p_rb and not p_rb.IsReadOnly:
            p_rb.Set(1)
    except:
        pass

    # Пытаемся разрешить wall joins
    try:
        WallUtils.AllowWallJoinAtEnd(wall, 0)
    except:
        pass
    try:
        WallUtils.AllowWallJoinAtEnd(wall, 1)
    except:
        pass

    return {
        "ok": True,
        "element_id": wall.Id.IntegerValue,
        "level_name": _elem_name(level),
        "wall_type_name": _elem_name(wall_type),
        "match": {
            "level": level_match,
            "wall_type": wt_match
        }
    }

def prim_create_floor(doc, p):
    _check_timeout("prim_create_floor")

    p = _as_py(p)
    if not isinstance(p, dict):
        return {"ok": False, "error": "params для create_floor не являются словарём"}

    level_keyword = str(_get(p, "level_keyword", "") or "")
    floor_type_keyword = str(_get(p, "floor_type_keyword", "") or "")

    level, level_match = _find_best(doc, Level, level_keyword, True)
    floor_type, ft_match = _find_best(doc, FloorType, floor_type_keyword, True)

    if not level:
        return {"ok": False, "error": "Level не найден"}
    if not floor_type:
        return {"ok": False, "error": "FloorType не найден"}

    boundary_mm = _get(p, "boundary_mm", None)

    if boundary_mm:
        curves = _build_closed_curves_from_boundary_mm(boundary_mm)
    else:
        origin_mm = _get(p, "origin_mm", [0, 0, 0])
        length_mm = _get(p, "length_mm", None)
        width_mm  = _get(p, "width_mm", None)
        curves = _build_rect_curves_from_origin(origin_mm, length_mm, width_mm)

    floor = _create_floor_compat(doc, curves, floor_type, level)

    return {
        "ok": True,
        "element_id": floor.Id.IntegerValue,
        "level_name": _elem_name(level),
        "floor_type_name": _elem_name(floor_type),
        "match": {
            "level": level_match,
            "floor_type": ft_match
        }
    }

def prim_create_room(doc, p):
    _check_timeout("prim_create_room")

    p = _as_py(p)
    if not isinstance(p, dict):
        return {"ok": False, "error": "params для create_room не являются словарём"}

    level_keyword = str(_get(p, "level_keyword", "") or "")
    center_mm = _get(p, "center_mm", [0, 0, 0])
    room_number = str(_get(p, "room_number", "") or "")
    room_name = str(_get(p, "room_name", "") or "")

    level, level_match = _find_best(doc, Level, level_keyword, True)
    if not level:
        return {"ok": False, "error": "Level не найден"}

    center_uv = _uv(center_mm)

    # Важно для Room
    try:
        doc.Regenerate()
    except:
        pass

    room = doc.Create.NewRoom(level, center_uv)
    if not room:
        return {"ok": False, "error": "Не удалось создать Room. Контур не замкнут или точка вне помещения."}

    _set_param_str(room, BuiltInParameter.ROOM_NUMBER, room_number)
    _set_param_str(room, BuiltInParameter.ROOM_NAME, room_name)

    return {
        "ok": True,
        "element_id": room.Id.IntegerValue,
        "level_name": _elem_name(level),
        "match": {
            "level": level_match
        }
    }

ACTION_MAP = {
    "create_wall": prim_create_wall,
    "create_floor": prim_create_floor,
    "create_room": prim_create_room,
}

# =========================================================
# ACTION EXECUTION
# =========================================================

def _classify_actions(actions):
    walls = []
    floors = []
    rooms = []
    others = []

    for i, act in enumerate(actions):
        act = _as_py(act)
        if not isinstance(act, dict):
            others.append({"index": i, "action": None, "params": None, "invalid": True})
            continue

        action_name = str(_get(act, "action", "") or "")
        params = _as_py(_get(act, "params", {}))

        item = {
            "index": i,
            "action": action_name,
            "params": params
        }

        if action_name == "create_wall":
            walls.append(item)
        elif action_name == "create_floor":
            floors.append(item)
        elif action_name == "create_room":
            rooms.append(item)
        else:
            others.append(item)

    return walls, floors, rooms, others

def _execute_phase(doc, phase_name, items, strict_mode):
    _check_timeout("phase_" + phase_name + "_start")

    phase_results = []
    created = 0
    errors = 0

    if not items:
        return phase_results, created, errors

    tx = Transaction(doc, "AiRevit: " + phase_name)
    started = False

    try:
        if str(tx.Start()) != "Started":
            raise Exception("Не удалось начать транзакцию фазы '{}'".format(phase_name))
        started = True

        if phase_name == "rooms":
            try:
                doc.Regenerate()
            except:
                pass

        for item in items:
            _check_timeout("phase_" + phase_name + "_loop")

            idx = _get(item, "index", -1)
            action_name = str(_get(item, "action", "") or "")
            params = _as_py(_get(item, "params", {}))

            fn = ACTION_MAP.get(action_name)
            if not fn:
                res = {
                    "ok": False,
                    "action": action_name,
                    "index": idx,
                    "error": "Неизвестное действие"
                }
                phase_results.append(res)
                errors += 1
                if strict_mode:
                    raise Exception("Strict mode: неизвестное действие '{}'".format(action_name))
                continue

            try:
                res = fn(doc, params)
                res["action"] = action_name
                res["index"] = idx
            except Exception:
                res = {
                    "ok": False,
                    "action": action_name,
                    "index": idx,
                    "error": traceback.format_exc()
                }

            phase_results.append(res)

            if _get(res, "ok", False):
                created += 1
            else:
                errors += 1
                if strict_mode:
                    raise Exception("Strict mode: ошибка в действии #{} '{}'".format(idx, action_name))

        tx.Commit()
        return phase_results, created, errors

    except:
        if started:
            try:
                tx.RollBack()
            except:
                pass
        raise

# =========================================================
# MAIN
# =========================================================

try:
    strict_mode = _to_bool(IN[1], False) if len(IN) > 1 else False
    timeout_sec = _set_timeout(IN[2] if len(IN) > 2 else 600)

    thought, actions, plan_status, meta = _parse_plan_input(IN[0])
    _check_timeout("plan_parsed")

    if thought == "ERROR" or "ERROR" in str(plan_status):
        raise ValueError("Node 4A вернул ошибку: " + str(plan_status))

    actions = _as_py(actions)
    if not isinstance(actions, list) or not actions:
        raise ValueError("План действий пуст")

    doc = DocumentManager.Instance.CurrentDBDocument
    if doc is None:
        raise ValueError("Не удалось получить текущий Revit document")

    walls, floors, rooms, others = _classify_actions(actions)

    pre_results = []
    pre_errors = 0
    if others:
        for item in others:
            pre_results.append({
                "ok": False,
                "phase": "precheck",
                "action": _get(item, "action", ""),
                "index": _get(item, "index", -1),
                "error": "Неразрешённое или некорректное действие"
            })
            pre_errors += 1
        if strict_mode:
            raise ValueError("Strict mode: найдены неразрешённые действия")

    tg = TransactionGroup(doc, "AiRevit: Execute Compiled Plan")
    tg_started = False

    try:
        if str(tg.Start()) != "Started":
            raise Exception("Не удалось начать TransactionGroup")
        tg_started = True

        all_results = []
        all_results.extend(pre_results)

        wall_results, wall_created, wall_errors = _execute_phase(doc, "walls", walls, strict_mode)
        all_results.extend([dict(r, **{"phase": "walls"}) for r in wall_results])

        floor_results, floor_created, floor_errors = _execute_phase(doc, "floors", floors, strict_mode)
        all_results.extend([dict(r, **{"phase": "floors"}) for r in floor_results])

        room_results, room_created, room_errors = _execute_phase(doc, "rooms", rooms, strict_mode)
        all_results.extend([dict(r, **{"phase": "rooms"}) for r in room_results])

        total_created = wall_created + floor_created + room_created
        total_errors = pre_errors + wall_errors + floor_errors + room_errors

        if total_created > 0:
            tg.Assimilate()
        else:
            tg.RollBack()

        if total_created > 0 and total_errors == 0:
            final_status = "success"
        elif total_created > 0 and total_errors > 0:
            final_status = "partial"
        else:
            final_status = "error"

        OUT = {
            "status": final_status,
            "thought": thought,
            "strict_mode": strict_mode,
            "timeout_sec": timeout_sec,
            "meta": meta if isinstance(meta, dict) else {},
            "summary": {
                "input_action_count": len(actions),
                "wall_actions": len(walls),
                "floor_actions": len(floors),
                "room_actions": len(rooms),
                "other_actions": len(others),
                "created_total": total_created,
                "errors_total": total_errors,
                "created_walls": wall_created,
                "created_floors": floor_created,
                "created_rooms": room_created,
                "errors_walls": wall_errors,
                "errors_floors": floor_errors,
                "errors_rooms": room_errors
            },
            "results": all_results
        }

    except Exception:
        if tg_started:
            try:
                tg.RollBack()
            except:
                pass
        raise

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
            "error": "Критическая ошибка в Node 5: " + traceback.format_exc()
        }
