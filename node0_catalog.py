# -*- coding: utf-8 -*-
# NODE 0 — Собирает каталог доступных типов в текущем Revit-документе
# OUT: dict - {"levels": [...], "wall_types": [...], "floor_types": [...]}

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import *

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

OUT = {"levels": [], "wall_types": [], "floor_types": []}

def _get_name(x):
    """Безопасное получение имени элемента (CPython3 + IronPython2)."""
    # CPython3: прямой доступ к .Name
    try:
        n = x.Name
        if n:
            return str(n)
    except:
        pass
    # IronPython2 fallback
    try:
        n = Element.Name.GetValue(x)
        if n:
            return str(n)
    except:
        pass
    # Для типов стен/полов: FamilyName
    try:
        n = x.FamilyName
        if n:
            return str(n)
    except:
        pass
    return ""

try:
    doc = DocumentManager.Instance.CurrentDBDocument

    # 1. Уровни (Level)
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    for lvl in levels:
        name = _get_name(lvl)
        if name:
            OUT["levels"].append(name)

    # 2. Типы стен (WallType)
    wall_types = FilteredElementCollector(doc).OfClass(WallType).ToElements()
    for wt in wall_types:
        name = _get_name(wt)
        if name:
            OUT["wall_types"].append(name)

    # 3. Типы полов (FloorType)
    floor_types = FilteredElementCollector(doc).OfClass(FloorType).ToElements()
    for ft in floor_types:
        name = _get_name(ft)
        if name:
            OUT["floor_types"].append(name)

except Exception as e:
    import traceback
    OUT = {"error": "Catalog collection failed: " + traceback.format_exc()}