import clr
import json
import traceback

clr.AddReference('RevitServices')
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import (
    XYZ, Line as RvtLine, Wall, WallType, WallKind,
    FilteredElementCollector, BuiltInCategory, BuiltInParameter,
    Level, FamilySymbol, Structure, UV,
    TextNote, TextNoteOptions, TextNoteType
)

# ── Константы ──
MM_TO_FEET   = 0.00328084
WALL_H_MM    = 3000
DOOR_H_MM    = 2100
DOOR_W_MM    = 900

def _elem_id(elem):
    try: return int(elem.Id.Value)
    except: pass
    try: return int(elem.Id.IntegerValue)
    except: return -1

def _get_name(x):
    try:
        n = x.Name
        if n: return str(n)
    except: pass
    return ""

def mm(v): return float(v) * MM_TO_FEET

# ─────────────────────────────────────────────
try:
    doc = DocumentManager.Instance.CurrentDBDocument

    file_path = str(IN[0])
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # ── Уровень ──
    levels = list(FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Levels)
        .WhereElementIsNotElementType().ToElements())
    level = None
    for lv in levels:
        n = _get_name(lv).lower()
        if "уровень 1" in n or "level 1" in n:
            level = lv; break
    if level is None and levels:
        level = levels[0]
    if level is None:
        OUT = "ERROR: нет уровней"; raise Exception(OUT)

    # ── Тип стены — только Basic / Базовая ──
    wall_types = list(FilteredElementCollector(doc).OfClass(WallType).ToElements())
    # Оставляем только стены с WallKind.Basic (не Curtain, не Stacked)
    basic_walls = [wt for wt in wall_types
                   if hasattr(wt, 'Kind') and str(wt.Kind) in ("0", "Basic", "WallKind.Basic")]
    if not basic_walls:
        # Фолбэк: исключаем витражи по имени
        basic_walls = [wt for wt in wall_types
                       if not any(k in _get_name(wt).lower()
                                  for k in ["витраж", "curtain", "составн", "stacked"])]
    # Выбираем первую "тонкую" стену (предпочитаем 200мм)
    wall_type = None
    for wt in basic_walls:
        if "200" in _get_name(wt):
            wall_type = wt; break
    if wall_type is None and basic_walls:
        wall_type = basic_walls[0]
    if wall_type is None:
        OUT = "ERROR: нет подходящего типа стены"; raise Exception(OUT)

    # ── Тип двери — первый попавшийся FamilySymbol из категории Doors ──
    door_symbols = list(FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Doors)
        .OfClass(FamilySymbol).ToElements())
    door_symbol = door_symbols[0] if door_symbols else None

    # ── Тип текстовой заметки ──
    text_types = list(FilteredElementCollector(doc).OfClass(TextNoteType).ToElements())
    text_type = text_types[0] if text_types else None

    # ─────────────────────────────────────────────
    # Функции
    # ─────────────────────────────────────────────
    def make_line(x1, y1, x2, y2):
        p1 = XYZ(mm(x1), mm(y1), 0)
        p2 = XYZ(mm(x2), mm(y2), 0)
        if p1.DistanceTo(p2) < 0.001:
            return None
        return RvtLine.CreateBound(p1, p2)

    def room_walls(room):
        x, y = float(room["x_mm"]), float(room["y_mm"])
        w, h = float(room["width_mm"]), float(room["height_mm"])
        return [
            make_line(x,   y,   x+w, y  ),
            make_line(x+w, y,   x+w, y+h),
            make_line(x+w, y+h, x,   y+h),
            make_line(x,   y+h, x,   y  ),
        ]

    # ─────────────────────────────────────────────
    # Старт транзакции
    # ─────────────────────────────────────────────
    TransactionManager.Instance.EnsureInTransaction(doc)

    # === 1. СТЕНЫ ===
    wall_segs = {}
    for room in data.get("rooms", []):
        for ln in room_walls(room):
            if ln is None: continue
            p1, p2 = ln.GetEndPoint(0), ln.GetEndPoint(1)
            ka = (round(p1.X,3), round(p1.Y,3))
            kb = (round(p2.X,3), round(p2.Y,3))
            key = tuple(sorted([ka, kb]))
            if key not in wall_segs:
                wall_segs[key] = ln

    created_walls, failed_walls = [], []
    wall_by_key = {}   # key -> Revit Wall object (нужно для дверей)
    for key, ln in wall_segs.items():
        try:
            w = Wall.Create(doc, ln, wall_type.Id, level.Id,
                            mm(WALL_H_MM), 0, False, False)
            created_walls.append(_elem_id(w))
            wall_by_key[key] = w
        except Exception as e:
            failed_walls.append(str(e))

    # === 2. ДВЕРИ (из openings в JSON) ===
    created_doors, failed_doors = [], []
    if door_symbol is not None:
        # Активируем символ если не активирован
        try:
            if not door_symbol.IsActive:
                door_symbol.Activate()
                doc.Regenerate()
        except: pass

        for op in data.get("openings", []):
            if op.get("type") != "internal_door":
                continue
            try:
                dx = float(op["x_mm"])
                dy = float(op["y_mm"])
                dw = float(op.get("width_mm", DOOR_W_MM))
                orient = op.get("orientation", "vertical")

                # Центр двери
                if orient == "vertical":
                    pt = XYZ(mm(dx), mm(dy + dw/2), 0)
                else:
                    pt = XYZ(mm(dx + dw/2), mm(dy), 0)

                # Ищем ближайшую стену из созданных
                host_wall = None
                min_dist = 9999.0
                for wobj in wall_by_key.values():
                    try:
                        lc = wobj.Location.Curve
                        dist = lc.Distance(pt)
                        if dist < min_dist:
                            min_dist = dist
                            host_wall = wobj
                    except: pass

                if host_wall is None or min_dist > mm(400):
                    failed_doors.append("op " + op.get("id","?") + ": wall not found nearby")
                    continue

                door = doc.Create.NewFamilyInstance(
                    pt, door_symbol, host_wall, level,
                    Structure.StructuralType.NonStructural
                )
                created_doors.append(_elem_id(door))
            except Exception as e:
                failed_doors.append(op.get("id","?") + ": " + str(e))

    # === 3. ПОДПИСИ ПОМЕЩЕНИЙ ===
    created_labels, failed_labels = [], []
    if text_type is not None:
        for room in data.get("rooms", []):
            try:
                cx = float(room["x_mm"]) + float(room["width_mm"]) / 2.0
                cy = float(room["y_mm"]) + float(room["height_mm"]) / 2.0
                pt = XYZ(mm(cx), mm(cy), 0)
                label = room.get("name", room.get("id", "?"))
                area  = room.get("generated_area_m2", "")
                text  = label + "\n" + str(area) + " m²" if area else label

                opts = TextNoteOptions(text_type.Id)
                tn = TextNote.Create(doc, doc.ActiveView.Id, pt, text, opts)
                created_labels.append(_elem_id(tn))
            except Exception as e:
                failed_labels.append(room.get("id","?") + ": " + str(e))

    TransactionManager.Instance.TransactionTaskDone()

    # ── Итоговый отчёт ──
    OUT = (
        "OK"
        + " | walls: "  + str(len(created_walls))
        + " | doors: "  + str(len(created_doors))
        + " | labels: " + str(len(created_labels))
        + " | wall_type: " + _get_name(wall_type)
        + " | level: "  + _get_name(level)
        + (" | wall_errors: "  + "; ".join(failed_walls)  if failed_walls  else "")
        + (" | door_errors: "  + "; ".join(failed_doors)  if failed_doors  else "")
        + (" | label_errors: " + "; ".join(failed_labels) if failed_labels else "")
    )

except Exception as e:
    OUT = "EXCEPTION: " + str(e) + "\n" + traceback.format_exc()
