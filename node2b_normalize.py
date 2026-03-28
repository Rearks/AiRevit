# -*- coding: utf-8 -*-
# NODE 2B — Normalize Semantic Intent (robust)
# IN[0] : list/.NET list - Output from Node 2A
# OUT   : dict - normalized semantic intent

import copy
import json
import traceback

OUT = {"status": "Node 2B: не запущен"}

DEFAULT_HEIGHT_MM = 3000
DEFAULT_UNITS = "mm"
DEFAULT_LAYOUT_TYPE = "single_level_rectangular"

try:
    string_types = (basestring,)
except:
    string_types = (str,)

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

def _to_float(v, d=None):
    try:
        return float(v)
    except:
        return d

def _to_int(v, d=None):
    try:
        return int(float(v))
    except:
        return d

def _positive_number(v):
    try:
        return float(v) > 0
    except:
        return False

def _normalize_space_kind(kind):
    k = str(kind or "").strip().lower()
    mapping = {
        u"кабинет": "office",
        u"офис": "office",
        u"office": "office",
        u"коридор": "corridor",
        u"corridor": "corridor",
        u"переговорная": "meeting",
        u"meeting": "meeting",
        u"санузел": "wc",
        u"wc": "wc",
        u"туалет": "wc",
        u"кухня": "kitchen",
        u"kitchen": "kitchen",
        u"лобби": "lobby",
        u"lobby": "lobby",
        u"кладовая": "storage",
        u"storage": "storage",
        u"комната": "room",
        u"room": "room"
    }
    return mapping.get(k, "room")

try:
    raw_in = IN[0]
    node2a_out = _as_py(raw_in)

    if not isinstance(node2a_out, (list, tuple)) or len(node2a_out) < 3:
        raise ValueError(
            "IN[0] должен быть output из Node 2A в виде [thought, intent_dict, status]. "
            "Сейчас пришёл тип: {}".format(str(type(node2a_out)))
        )

    thought = str(node2a_out[0])
    intent = _as_py(node2a_out[1])
    status = str(node2a_out[2])

    if thought == "ERROR" or "ERROR" in status:
        raise ValueError("Node 2A вернул ошибку: " + status)

    # Иногда intent может прийти строкой
    if _is_string(intent):
        try:
            intent = json.loads(intent)
        except:
            pass

    intent = _as_py(intent)

    if not isinstance(intent, dict):
        raise ValueError(
            "Intent должен быть словарём. Получено: {} | Значение: {}".format(
                str(type(intent)), str(intent)[:500]
            )
        )

    normalized = copy.deepcopy(intent)

    raw_warnings = normalized.get("_warnings", [])
    raw_warnings = _as_py(raw_warnings)
    warnings = raw_warnings if isinstance(raw_warnings, list) else []

    # project_scope
    project_scope = _as_py(normalized.get("project_scope", {}))
    if not isinstance(project_scope, dict):
        project_scope = {}

    project_scope["units"] = DEFAULT_UNITS
    project_scope["layout_type"] = DEFAULT_LAYOUT_TYPE
    project_scope["level_keyword"] = str(project_scope.get("level_keyword", "") or "").strip()
    normalized["project_scope"] = project_scope

    # preferences
    preferences = _as_py(normalized.get("preferences", {}))
    if not isinstance(preferences, dict):
        preferences = {}
    preferences["wall_type_keyword"] = str(preferences.get("wall_type_keyword", "") or "").strip()
    preferences["floor_type_keyword"] = str(preferences.get("floor_type_keyword", "") or "").strip()
    normalized["preferences"] = preferences

    # constraints
    constraints = _as_py(normalized.get("constraints", {}))
    if not isinstance(constraints, dict):
        constraints = {}
    constraints["orthogonal_only"] = True
    constraints["rectangular_spaces_only"] = True
    normalized["constraints"] = constraints

    raw_spaces = _as_py(normalized.get("spaces", []))
    if not isinstance(raw_spaces, list) or not raw_spaces:
        raise ValueError("После валидации spaces должен быть непустым списком")

    final_spaces = []
    used_ids = set()

    for i, sp in enumerate(raw_spaces):
        sp = _as_py(sp)
        if not isinstance(sp, dict):
            continue

        sid = str(sp.get("id", "space_{}".format(i + 1))).strip()
        kind = _normalize_space_kind(sp.get("kind", "room"))
        name = str(sp.get("name", "") or "").strip()
        count = _to_int(sp.get("count", 1), 1)
        if count is None or count < 1:
            count = 1

        width_mm = _to_float(sp.get("width_mm"))
        length_mm = _to_float(sp.get("length_mm"))
        height_mm = _to_float(sp.get("height_mm"), DEFAULT_HEIGHT_MM)

        # одна сторона -> квадрат
        if width_mm is None and length_mm is not None:
            width_mm = length_mm
        if length_mm is None and width_mm is not None:
            length_mm = width_mm

        if kind != "corridor":
            if not _positive_number(width_mm) or not _positive_number(length_mm):
                raise ValueError("Space '{}' должен иметь положительные width_mm и length_mm".format(sid))

        if not _positive_number(height_mm):
            height_mm = DEFAULT_HEIGHT_MM
            warnings.append("Space '{}' получил высоту по умолчанию 3000 мм".format(sid))

        for idx in range(count):
            if count == 1:
                new_id = sid
                new_name = name if name else sid
            else:
                new_id = "{}_{}".format(sid, idx + 1)
                new_name = "{} {}".format(name, idx + 1) if name else new_id

            base_id = new_id
            n = 1
            while new_id in used_ids:
                n += 1
                new_id = "{}_dup{}".format(base_id, n)

            used_ids.add(new_id)

            final_space = {
                "id": new_id,
                "kind": kind,
                "name": new_name,
                "width_mm": width_mm,
                "length_mm": length_mm,
                "height_mm": height_mm
            }

            final_spaces.append(final_space)

    raw_relationships = _as_py(normalized.get("relationships", []))
    if not isinstance(raw_relationships, list):
        raw_relationships = []

    valid_ids = set(sp["id"] for sp in final_spaces)
    final_relationships = []

    for rel in raw_relationships:
        rel = _as_py(rel)
        if not isinstance(rel, dict):
            continue

        rtype = str(rel.get("type", "") or "").strip().lower()
        rf = str(rel.get("from", "") or "").strip()
        rt = str(rel.get("to", "") or "").strip()

        if rf in valid_ids and rt in valid_ids and rf != rt:
            final_relationships.append({
                "type": rtype,
                "from": rf,
                "to": rt
            })
        else:
            warnings.append("Relationship '{}' -> '{}' пропущен после нормализации".format(rf, rt))

    normalized["spaces"] = final_spaces
    normalized["relationships"] = final_relationships

    for idx, sp in enumerate(normalized["spaces"]):
        sp["room_number"] = str(100 + idx + 1)

    normalized["version"] = "1.0"
    normalized["_warnings"] = warnings

    OUT = {
        "status": "ok",
        "thought": thought,
        "intent": normalized,
        "warnings": warnings
    }

except Exception:
    OUT = {
        "status": "error",
        "error": "Критическая ошибка в Node 2B: " + traceback.format_exc()
    }
