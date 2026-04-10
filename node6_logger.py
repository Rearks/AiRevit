# -*- coding: utf-8 -*-
# NODE 6 — Pipeline Logger
# IN[0] : str       - User prompt (original)
# IN[1] : str/dict  - Node 1A raw response (optional)
# IN[2] : list/dict - Node 2A/2B output (optional)
# IN[3] : dict      - Node 3A/3B topology output (optional)
# IN[4] : list/dict - Node 4A/4B compile plan output (optional)
# IN[5] : dict      - Node 5 execution result (optional)
# IN[6] : str       - Log directory path (optional, default: same folder)
#
# OUT   : dict - {"status": "ok"/"error", "log_file": "...", "summary": {...}}
#
# Saves the full pipeline state to a timestamped JSON file.
# This creates a growing dataset for:
#   - debugging
#   - benchmark regression testing
#   - future RAG / fine-tuning
#   - statistics

import json
import os
import time
import traceback

OUT = {"status": "Node 6: не запущен"}

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

def _safe_get_input(index, default=None):
    """Безопасно получает вход из IN."""
    try:
        v = IN[index]
        if v is None:
            return default
        return _as_py(v)
    except:
        return default

def _make_serializable(obj):
    """Гарантирует, что объект сериализуем в JSON."""
    if obj is None:
        return None

    if isinstance(obj, (bool,)):
        return obj

    if isinstance(obj, (int, float)):
        return obj

    if _is_string(obj):
        return obj

    if isinstance(obj, dict):
        d = {}
        for k, v in obj.items():
            d[str(k)] = _make_serializable(v)
        return d

    if isinstance(obj, (list, tuple)):
        return [_make_serializable(x) for x in obj]

    # fallback
    return str(obj)

def _detect_pipeline_status(exec_result):
    """Определяет общий статус пайплайна по результату Node 5."""
    if exec_result is None:
        return "incomplete"

    if isinstance(exec_result, dict):
        status = str(_get(exec_result, "status", "unknown")).lower()
        if status in ("success", "partial", "error", "timeout"):
            return status

    return "unknown"

def _count_elements(exec_result):
    """Считает созданные элементы из результата Node 5."""
    if not isinstance(exec_result, dict):
        return {}

    summary = _as_py(_get(exec_result, "summary", {}))
    if not isinstance(summary, dict):
        return {}

    return {
        "walls": _get(summary, "created_walls", 0),
        "floors": _get(summary, "created_floors", 0),
        "rooms": _get(summary, "created_rooms", 0),
        "total": _get(summary, "created_total", 0),
        "errors": _get(summary, "errors_total", 0)
    }

# =============================================
# ГЛАВНАЯ ЛОГИКА
# =============================================

try:
    # Собираем данные из всех входов
    prompt = _safe_get_input(0, "")
    if _is_string(prompt):
        prompt = str(prompt).strip()
    else:
        prompt = str(prompt)

    llm_response = _safe_get_input(1)
    parse_result = _safe_get_input(2)
    topology_result = _safe_get_input(3)
    plan_result = _safe_get_input(4)
    exec_result = _safe_get_input(5)

    log_dir = _safe_get_input(6)
    if not _is_string(log_dir) or not log_dir:
        # По умолчанию — подпапка logs в директории скрипта
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
        except:
            script_dir = r"C:\Users\kraer\AiRevit"
        log_dir = os.path.join(script_dir, "logs")

    log_dir = str(log_dir).strip()

    # Создаем директорию если нет
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Формируем имя файла
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    # Краткое содержание промпта для имени файла
    prompt_slug = prompt[:40].strip()
    for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|', '\n', '\r']:
        prompt_slug = prompt_slug.replace(ch, '_')
    prompt_slug = prompt_slug.strip('_')

    if not prompt_slug:
        prompt_slug = "no_prompt"

    filename = "log_{}_{}.json".format(timestamp, prompt_slug)
    filepath = os.path.join(log_dir, filename)

    # Определяем статус пайплайна
    pipeline_status = _detect_pipeline_status(exec_result)
    element_counts = _count_elements(exec_result)

    # Собираем лог
    log_entry = {
        "version": "1.0",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "timestamp_unix": time.time(),
        "pipeline_status": pipeline_status,

        "prompt": prompt,

        "llm_response": _make_serializable(llm_response),
        "parse_result": _make_serializable(parse_result),
        "topology_result": _make_serializable(topology_result),
        "plan_result": _make_serializable(plan_result),
        "execution_result": _make_serializable(exec_result),

        "summary": {
            "pipeline_status": pipeline_status,
            "element_counts": element_counts,
            "prompt_length": len(prompt),
            "has_llm_response": llm_response is not None,
            "has_topology": topology_result is not None,
            "has_plan": plan_result is not None,
            "has_execution": exec_result is not None
        }
    }

    # Записываем
    json_text = json.dumps(log_entry, ensure_ascii=False, indent=2)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(json_text)

    OUT = {
        "status": "ok",
        "log_file": filepath,
        "log_dir": log_dir,
        "timestamp": log_entry["timestamp"],
        "pipeline_status": pipeline_status,
        "summary": log_entry["summary"]
    }

except Exception:
    OUT = {
        "status": "error",
        "error": "Критическая ошибка в Node 6 (Logger): " + traceback.format_exc()
    }
