# -*- coding: utf-8 -*-
# NODE 4B — Validate Compile Plan
# IN[0] : list - Output from Node 4A [thought, actions, status, meta]
# OUT   : dict - {"status": "ok"/"error", "thought", "actions", "meta", "validation"}
#
# Validates action plan BEFORE execution in Node 5.
# If valid   → status "ok", plan passes through to Node 5
# If warning → status "ok", warnings added, still passes through
# If error   → status "error", plan blocked from execution
#
# Pipeline: ... → Node 4A → [Node 4B] → Node 5
#
# Checks:
#   1. Plan is non-empty
#   2. All actions have valid names and params
#   3. No zero-length walls
#   4. No duplicate wall segments
#   5. Floors have positive dimensions
#   6. Room centers are not exactly on wall boundaries
#   7. Heights are positive
#   8. All required params present for each action type

import traceback

OUT = {"status": "Node 4B: не запущен"}

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

def _n(v):
    """Нормализация числа для ключей."""
    try:
        return round(float(v), 3)
    except:
        return 0.0

# =============================================
# ПАРСИНГ ВХОДА
# =============================================

def _parse_plan_input(raw):
    """Парсит вход от Node 4A: [thought, actions, status, meta]."""
    raw = _as_py(raw)

    if isinstance(raw, list) and len(raw) >= 3:
        thought = str(raw[0])
        actions = _as_py(raw[1])
        status = str(raw[2])
        meta = _as_py(raw[3]) if len(raw) > 3 else {}
        return thought, actions, status, meta

    if isinstance(raw, dict):
        thought = str(_get(raw, "thought", ""))
        actions = _as_py(_get(raw, "actions", []))
        status = str(_get(raw, "status", ""))
        meta = _as_py(_get(raw, "meta", {}))
        return thought, actions, status, meta

    raise ValueError("IN[0] должен быть output из Node 4A: [thought, actions, status, meta]")

# =============================================
# ВАЛИДАЦИИ
# =============================================

ALLOWED_ACTIONS = {"create_wall", "create_floor", "create_room"}

REQUIRED_PARAMS = {
    "create_wall": ["level_keyword", "wall_type_keyword", "start_mm", "end_mm", "height_mm"],
    "create_floor": ["level_keyword", "floor_type_keyword"],
    "create_room": ["level_keyword", "center_mm"],
}


def validate_actions_structure(actions, errors, warnings):
    """Проверяет базовую структуру каждого action."""
    if not isinstance(actions, list):
        errors.append("'actions' не является списком")
        return

    if not actions:
        errors.append("Список действий пуст — нечего выполнять")
        return

    for i, act in enumerate(actions):
        act = _as_py(act)
        label = "Action #{} ".format(i + 1)

        if not isinstance(act, dict):
            errors.append(label + "не является словарём")
            continue

        action_name = str(_get(act, "action", "")).strip()
        if not action_name:
            errors.append(label + "отсутствует поле 'action'")
            continue

        if action_name not in ALLOWED_ACTIONS:
            errors.append(label + "неизвестное действие '{}'".format(action_name))
            continue

        params = _as_py(_get(act, "params", {}))
        if not isinstance(params, dict):
            errors.append(label + "поле 'params' не является словарём")
            continue

        # Проверяем наличие обязательных параметров
        required = REQUIRED_PARAMS.get(action_name, [])
        for req_param in required:
            if req_param not in params:
                # level_keyword и type keywords могут быть пустыми строками — это ок
                if req_param.endswith("_keyword"):
                    continue
                errors.append(label + "'{}': отсутствует обязательный параметр '{}'".format(
                    action_name, req_param
                ))


def validate_walls(actions, errors, warnings):
    """Проверяет стены: нулевая длина, дубликаты сегментов, высота."""
    wall_segments = []  # для поиска дубликатов

    for i, act in enumerate(actions):
        act = _as_py(act)
        if not isinstance(act, dict):
            continue

        if str(_get(act, "action", "")) != "create_wall":
            continue

        label = "Wall #{} (action #{})".format(len(wall_segments) + 1, i + 1)
        params = _as_py(_get(act, "params", {}))
        if not isinstance(params, dict):
            continue

        # Координаты
        start_mm = _as_py(_get(params, "start_mm"))
        end_mm = _as_py(_get(params, "end_mm"))

        if not isinstance(start_mm, list) or len(start_mm) < 2:
            errors.append("{}: start_mm некорректный".format(label))
            continue

        if not isinstance(end_mm, list) or len(end_mm) < 2:
            errors.append("{}: end_mm некорректный".format(label))
            continue

        sx = _to_float(start_mm[0], 0)
        sy = _to_float(start_mm[1], 0)
        ex = _to_float(end_mm[0], 0)
        ey = _to_float(end_mm[1], 0)

        # 1. Нулевая длина
        dx = ex - sx
        dy = ey - sy
        seg_len = (dx * dx + dy * dy) ** 0.5

        if seg_len < EPS:
            errors.append("{}: стена нулевой длины (start=[{},{}], end=[{},{}])".format(
                label, sx, sy, ex, ey
            ))
            continue

        # 2. Маленькая стена (предупреждение)
        if seg_len < 50.0:  # меньше 50 мм — подозрительно
            warnings.append("{}: очень короткая стена ({:.1f} мм)".format(label, seg_len))

        # 3. Высота
        height_mm = _to_float(_get(params, "height_mm"), None)
        if height_mm is None or not _is_positive(height_mm):
            errors.append("{}: height_mm должен быть > 0".format(label))

        # 4. Собираем для проверки дубликатов
        # Нормализуем: всегда от меньшей точки к большей
        p1 = (_n(min(sx, ex)), _n(min(sy, ey)))
        p2 = (_n(max(sx, ex)), _n(max(sy, ey)))

        # Для точного сравнения нужно учитывать ориентацию
        if abs(sy - ey) < EPS:  # горизонтальная
            seg_key = ("H", _n(sy), _n(min(sx, ex)), _n(max(sx, ex)))
        elif abs(sx - ex) < EPS:  # вертикальная
            seg_key = ("V", _n(sx), _n(min(sy, ey)), _n(max(sy, ey)))
        else:  # наклонная (не ожидается, но на всякий случай)
            seg_key = ("D", p1[0], p1[1], p2[0], p2[1])

        wall_segments.append((seg_key, label))

    # 5. Проверка дубликатов
    seen = {}
    for seg_key, label in wall_segments:
        if seg_key in seen:
            errors.append("Дубликат стены: {} совпадает с {}".format(label, seen[seg_key]))
        else:
            seen[seg_key] = label


def validate_floors(actions, errors, warnings):
    """Проверяет полы: положительные размеры."""
    floor_idx = 0

    for i, act in enumerate(actions):
        act = _as_py(act)
        if not isinstance(act, dict):
            continue

        if str(_get(act, "action", "")) != "create_floor":
            continue

        floor_idx += 1
        label = "Floor #{} (action #{})".format(floor_idx, i + 1)
        params = _as_py(_get(act, "params", {}))
        if not isinstance(params, dict):
            continue

        # Если задан boundary_mm
        boundary_mm = _as_py(_get(params, "boundary_mm"))
        if boundary_mm is not None:
            if not isinstance(boundary_mm, list) or len(boundary_mm) < 3:
                errors.append("{}: boundary_mm должен содержать >= 3 точек".format(label))
            continue

        # Если задан origin + length + width
        origin = _as_py(_get(params, "origin_mm"))
        length_mm = _to_float(_get(params, "length_mm"), None)
        width_mm = _to_float(_get(params, "width_mm"), None)

        if origin is not None:
            if not isinstance(origin, list) or len(origin) < 2:
                errors.append("{}: origin_mm некорректный".format(label))

        if length_mm is None or not _is_positive(length_mm):
            errors.append("{}: length_mm должен быть > 0 (сейчас: {})".format(label, length_mm))

        if width_mm is None or not _is_positive(width_mm):
            errors.append("{}: width_mm должен быть > 0 (сейчас: {})".format(label, width_mm))


def validate_rooms(actions, errors, warnings):
    """Проверяет rooms: center существует и не на нулевой точке (подозрительно)."""
    room_idx = 0

    # Собираем все стены для проверки, что center не на границе
    wall_segments = []
    for act in actions:
        act = _as_py(act)
        if not isinstance(act, dict):
            continue
        if str(_get(act, "action", "")) != "create_wall":
            continue
        params = _as_py(_get(act, "params", {}))
        if not isinstance(params, dict):
            continue

        start_mm = _as_py(_get(params, "start_mm"))
        end_mm = _as_py(_get(params, "end_mm"))
        if isinstance(start_mm, list) and isinstance(end_mm, list):
            if len(start_mm) >= 2 and len(end_mm) >= 2:
                wall_segments.append((
                    _to_float(start_mm[0], 0), _to_float(start_mm[1], 0),
                    _to_float(end_mm[0], 0), _to_float(end_mm[1], 0)
                ))

    for i, act in enumerate(actions):
        act = _as_py(act)
        if not isinstance(act, dict):
            continue

        if str(_get(act, "action", "")) != "create_room":
            continue

        room_idx += 1
        label = "Room #{} (action #{})".format(room_idx, i + 1)
        params = _as_py(_get(act, "params", {}))
        if not isinstance(params, dict):
            continue

        center_mm = _as_py(_get(params, "center_mm"))
        if not isinstance(center_mm, list) or len(center_mm) < 2:
            errors.append("{}: center_mm отсутствует или некорректный".format(label))
            continue

        cx = _to_float(center_mm[0], None)
        cy = _to_float(center_mm[1], None)

        if cx is None or cy is None:
            errors.append("{}: center_mm содержит нечисловые значения".format(label))
            continue

        # Проверяем, не лежит ли center точно на линии стены
        for sx, sy, ex, ey in wall_segments:
            on_wall = False

            # Горизонтальная стена
            if abs(sy - ey) < EPS:
                if abs(cy - sy) < EPS:
                    min_x = min(sx, ex)
                    max_x = max(sx, ex)
                    if min_x - EPS <= cx <= max_x + EPS:
                        on_wall = True

            # Вертикальная стена
            elif abs(sx - ex) < EPS:
                if abs(cx - sx) < EPS:
                    min_y = min(sy, ey)
                    max_y = max(sy, ey)
                    if min_y - EPS <= cy <= max_y + EPS:
                        on_wall = True

            if on_wall:
                warnings.append(
                    "{}: center_mm [{}, {}] лежит на линии стены "
                    "([{},{}] -> [{},{}]). Room может не создаться.".format(
                        label, cx, cy, sx, sy, ex, ey
                    )
                )
                break  # достаточно одного предупреждения


def validate_action_counts(actions, errors, warnings):
    """Проверяет соотношение типов действий."""
    counts = {"create_wall": 0, "create_floor": 0, "create_room": 0, "other": 0}

    for act in actions:
        act = _as_py(act)
        if not isinstance(act, dict):
            counts["other"] += 1
            continue
        action_name = str(_get(act, "action", ""))
        if action_name in counts:
            counts[action_name] += 1
        else:
            counts["other"] += 1

    # Стены есть, но нет комнат
    if counts["create_wall"] > 0 and counts["create_room"] == 0:
        warnings.append(
            "Есть {} стен, но нет ни одной Room. "
            "Помещения не будут определены.".format(counts["create_wall"])
        )

    # Комнаты есть, но нет стен
    if counts["create_room"] > 0 and counts["create_wall"] == 0:
        warnings.append(
            "Есть {} Room, но нет ни одной стены. "
            "Room не сможет определить свои границы.".format(counts["create_room"])
        )

    # Стены есть, но нет полов
    if counts["create_wall"] > 0 and counts["create_floor"] == 0:
        warnings.append("Есть стены, но нет полов.")

    return counts


# =============================================
# ГЛАВНАЯ ЛОГИКА
# =============================================

try:
    raw_in = IN[0]
    thought, actions, plan_status, meta = _parse_plan_input(raw_in)

    # Проверяем статус от Node 4A
    if thought == "ERROR" or "ERROR" in str(plan_status):
        OUT = {
            "status": "error",
            "error": "Node 4A вернул ошибку: " + str(plan_status),
            "source": "node4b_passthrough"
        }

    else:
        actions = _as_py(actions)
        if not isinstance(actions, list):
            actions = []

        if not isinstance(meta, dict):
            meta = {}

        errors = []
        warnings = []

        # === 1. Структурная валидация ===
        validate_actions_structure(actions, errors, warnings)

        # === 2. Валидация стен ===
        validate_walls(actions, errors, warnings)

        # === 3. Валидация полов ===
        validate_floors(actions, errors, warnings)

        # === 4. Валидация комнат ===
        validate_rooms(actions, errors, warnings)

        # === 5. Соотношение типов ===
        counts = validate_action_counts(actions, errors, warnings)

        # === Формируем выход ===
        validation = {
            "errors": errors,
            "warnings": warnings,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "action_counts": counts,
            "validated": len(errors) == 0
        }

        if errors:
            # БЛОКИРУЕМ — не пускаем в Node 5
            OUT = {
                "status": "error",
                "error": "Compile plan validation failed",
                "thought": thought,
                "actions": actions,
                "meta": meta,
                "validation": validation
            }
        else:
            # ПРОПУСКАЕМ — формат совместим с Node 5
            # Передаём в формате [thought, actions, status, meta]
            # чтобы Node 5 мог распарсить стандартным способом
            OUT = [thought, actions, "OK", {
                "original_meta": meta,
                "validation": validation
            }]

except Exception:
    OUT = {
        "status": "error",
        "error": "Критическая ошибка в Node 4B: " + traceback.format_exc()
    }
