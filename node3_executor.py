# -*- coding: utf-8 -*-
# NODE 3 — Executor: выполняет JSON action-план через библиотеку примитивов
# IN[0] : list - Output from Node 2: [thought, actions_list, status]
# OUT   : dict - {"status": "success/partial/error", "thought": ..., "results": [...]}

import traceback

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import *

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

try:
    from System.Collections.Generic import List as NetList
    from System.Collections.Generic import Dictionary
except:
    NetList = None
    Dictionary = None # Fallback если импорт не удался

OUT = {"status": "Node 3: не запущен"}
MM = 1.0 / 304.8  # мм -> футы

# =============================================
# УНИВЕРСАЛЬНЫЕ УТИЛИТЫ (КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ)
# =============================================

def _get(d, key, default=None):
    """
    Универсальная функция для получения значения из словаря.
    Работает и с Python dict, и с .NET Dictionary.
    """
    if hasattr(d, 'get'):  # Если это Python dict, используем .get()
        return d.get(key, default)
    # Если это .NET Dictionary, используем .ContainsKey()
    if Dictionary is not None and isinstance(d, Dictionary):
        if d.ContainsKey(key):
            return d[key]
    return default

# Остальные утилиты, обновленные для использования _get
def _to_float(v, d=0.0):
    try: return float(v)
    except: return d

def _elem_name(x):
    try: return str(Element.Name.GetValue(x) or "")
    except: pass
    try: return str(x.Name or "")
    except: pass
    return ""

def _collect(doc, cls):
    return list(FilteredElementCollector(doc).OfClass(cls))

def _find(doc, cls, keyword="", fallback_first=True):
    items = _collect(doc, cls)
    if not items: return None
    kw = str(keyword or "").strip().lower()
    if not kw: return items[0]
    for x in items:
        if kw in _elem_name(x).lower():
            return x
    return items[0] if fallback_first else None

def _pt(arr_mm):
    if not isinstance(arr_mm, (list, tuple)): arr_mm = [0, 0, 0]
    x = _to_float(arr_mm[0], 0.0) if len(arr_mm) > 0 else 0.0
    y = _to_float(arr_mm[1], 0.0) if len(arr_mm) > 1 else 0.0
    z = _to_float(arr_mm[2], 0.0) if len(arr_mm) > 2 else 0.0
    return XYZ(x * MM, y * MM, z * MM)

def _uv(arr_mm):
    if not isinstance(arr_mm, (list, tuple)): arr_mm = [0, 0, 0]
    x = _to_float(arr_mm[0], 0.0) if len(arr_mm) > 0 else 0.0
    y = _to_float(arr_mm[1], 0.0) if len(arr_mm) > 1 else 0.0
    return UV(x * MM, y * MM)

def _set_param_str(el, bip, value):
    if value is None or value == "": return
    p = el.get_Parameter(bip)
    if p and not p.IsReadOnly:
        p.Set(str(value))

def _create_floor_compat(doc, loop, ft, level):
    if hasattr(Floor, "Create"):
        try:
            loops = NetList[CurveLoop]() if NetList else []
            loops.Add(loop)
            return Floor.Create(doc, loops, ft.Id, level.Id)
        except Exception as e_new:
            try: # Fallback к старому API
                ca = CurveArray()
                for c in loop: ca.Append(c)
                return doc.Create.NewFloor(ca, ft, level, False)
            except Exception as e_old:
                raise Exception("Floor creation failed. New API: {} | Old API: {}".format(e_new, e_old))
    else: # Если Floor.Create вообще нет
        ca = CurveArray()
        for c in loop: ca.Append(c)
        return doc.Create.NewFloor(ca, ft, level, False)

# =============================================
# ПРИМИТИВЫ (обновлены для использования _get)
# =============================================

def prim_create_wall(doc, p):
    level = _find(doc, Level, _get(p, "level_keyword", ""))
    wt = _find(doc, WallType, _get(p, "wall_type_keyword", ""))
    if not level or not wt: return {"ok": False, "error": "Level или WallType не найден"}
    
    start = _pt(_get(p, "start_mm", [0, 0, 0]))
    end = _pt(_get(p, "end_mm", [1000, 0, 0]))
    h = _to_float(_get(p, "height_mm", 3000)) * MM
    
    wall = Wall.Create(doc, Line.CreateBound(start, end), wt.Id, level.Id, h, 0.0, False, False)
    return {"ok": True, "element_id": wall.Id.IntegerValue}

def prim_create_floor(doc, p):
    level = _find(doc, Level, _get(p, "level_keyword", ""))
    ft = _find(doc, FloorType, _get(p, "floor_type_keyword", ""))
    if not level or not ft: return {"ok": False, "error": "Level или FloorType не найден"}

    o = _get(p, "origin_mm", [0, 0, 0])
    L = _to_float(_get(p, "length_mm", 5000))
    W = _to_float(_get(p, "width_mm", L))
    
    x0, y0 = _to_float(o[0]), _to_float(o[1])
    
    pts = [_pt([x0, y0, 0]), _pt([x0 + L, y0, 0]), _pt([x0 + L, y0 + W, 0]), _pt([x0, y0 + W, 0])]
    loop = CurveLoop()
    for i in range(4): loop.Append(Line.CreateBound(pts[i], pts[(i+1)%4]))
    
    floor = _create_floor_compat(doc, loop, ft, level)
    return {"ok": True, "element_id": floor.Id.IntegerValue}

def prim_create_room(doc, p):
    level = _find(doc, Level, _get(p, "level_keyword", ""))
    if not level: return {"ok": False, "error": "Level не найден"}
    
    center = _get(p, "center_mm", [2500, 2500, 0])
    doc.Regenerate()
    room = doc.Create.NewRoom(level, _uv(center))
    if not room: return {"ok": False, "error": "Не удалось создать Room. Контур не замкнут?"}
    
    _set_param_str(room, BuiltInParameter.ROOM_NUMBER, _get(p, "room_number", ""))
    _set_param_str(room, BuiltInParameter.ROOM_NAME, _get(p, "room_name", ""))
    
    return {"ok": True, "element_id": room.Id.IntegerValue}

def prim_create_room_box(doc, p):
    results = []
    
    level_kw = _get(p, "level_keyword", "")
    wall_kw = _get(p, "wall_type_keyword", "")
    floor_kw = _get(p, "floor_type_keyword", "")
    
    level = _find(doc, Level, level_kw)
    wt = _find(doc, WallType, wall_kw)
    if not level or not wt: return {"ok": False, "error": "Level или WallType не найден"}
    
    o = _get(p, "origin_mm", [0, 0, 0])
    L = _to_float(_get(p, "length_mm", 5000))
    W = _to_float(_get(p, "width_mm", L))
    H = _to_float(_get(p, "height_mm", 3000))
    x0, y0 = _to_float(o[0]), _to_float(o[1])
    
    wall_ids = []
    pts = [_pt([x0, y0, 0]), _pt([x0 + L, y0, 0]), _pt([x0 + L, y0 + W, 0]), _pt([x0, y0 + W, 0])]
    for i in range(4):
        wall = Wall.Create(doc, Line.CreateBound(pts[i], pts[(i+1)%4]), wt.Id, level.Id, H * MM, 0.0, False, False)
        wall_ids.append(wall.Id.IntegerValue)
    results.append({"element": "walls", "ids": wall_ids})
    
    floor_res = prim_create_floor(doc, p)
    results.append({"element": "floor", "result": floor_res})
    
    room_res = prim_create_room(doc, p)
    results.append({"element": "room", "result": room_res})
    
    ok = _get(floor_res, "ok", False) and _get(room_res, "ok", False)
    return {"ok": ok, "details": results}

# =============================================
# ДИСПЕТЧЕР И ГЛАВНАЯ ЛОГИКА (обновлены для _get)
# =============================================

ACTION_MAP = {
    "create_wall": prim_create_wall,
    "create_room_box": prim_create_room_box,
    "create_floor": prim_create_floor,
    "create_room": prim_create_room,
}

try:
    node2_out = IN[0]
    if not isinstance(node2_out, (list, tuple)) or len(node2_out) < 3:
        raise ValueError("IN[0] должен быть списком из Node 2")

    thought = str(node2_out[0])
    actions_list = node2_out[1]
    parse_status = str(node2_out[2])

    if thought == "ERROR" or "ERROR" in parse_status:
        raise ValueError("Node 2 вернул ошибку: " + parse_status)
    if not actions_list:
        raise ValueError("Список actions пустой")

    doc = DocumentManager.Instance.CurrentDBDocument
    tx = Transaction(doc, "AiRevit: JSON Plan")
    started = False
    try:
        if str(tx.Start()) != "Started": raise Exception("Не удалось начать транзакцию")
        started = True
        
        results, errors_count = [], 0
        for act in actions_list:
            action_name = _get(act, "action", "")
            params = _get(act, "params", {})
            fn = ACTION_MAP.get(action_name)
            
            if not fn:
                res = {"action": action_name, "ok": False, "error": "Неизвестное действие"}
            else:
                try:
                    res = fn(doc, params)
                    res["action"] = action_name
                except:
                    res = {"action": action_name, "ok": False, "error": traceback.format_exc()}
            
            results.append(res)
            if not _get(res, "ok", False):
                errors_count += 1
        
        tx.Commit()

        status = "success"
        if errors_count > 0:
            status = "partial" if errors_count < len(actions_list) else "error"
        
        OUT = {"status": status, "thought": thought, "results": results}

    except:
        if started: tx.RollBack()
        raise

except Exception:
    OUT = {"status": "error", "error": "Критическая ошибка в Node 3: " + traceback.format_exc()}