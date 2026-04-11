import clr
import json
import traceback

clr.AddReference('ProtoGeometry')
from Autodesk.DesignScript.Geometry import Point, Polygon

# IN[0] = путь к layout_solution.json
# IN[1] = scale, например 0.001 (мм -> м)

try:
    file_path = str(IN[0])

    scale = 0.001
    try:
        if len(IN) > 1 and IN[1] is not None:
            s = float(IN[1])
            if s > 0:
                scale = s
    except:
        pass

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    def rect_to_polygon(x, y, w, h, s=1.0):
        if w <= 0 or h <= 0:
            return None
        p1 = Point.ByCoordinates(x * s, y * s, 0)
        p2 = Point.ByCoordinates((x + w) * s, y * s, 0)
        p3 = Point.ByCoordinates((x + w) * s, (y + h) * s, 0)
        p4 = Point.ByCoordinates(x * s, (y + h) * s, 0)
        return Polygon.ByPoints([p1, p2, p3, p4])

    def room_center(x, y, w, h, s=1.0):
        return Point.ByCoordinates((x + w / 2.0) * s, (y + h / 2.0) * s, 0)

    # Boundary
    bd = data.get("boundary", {})
    boundary = None
    bw = float(bd.get("width_mm", 0))
    bh = float(bd.get("height_mm", 0))
    if bw > 0 and bh > 0:
        boundary = rect_to_polygon(
            float(bd.get("x_mm", 0)),
            float(bd.get("y_mm", 0)),
            bw, bh, scale
        )

    # Rooms
    room_polygons = []
    room_labels = []
    room_centers = []
    room_kinds = []

    for room in data.get("rooms", []):
        x = float(room["x_mm"])
        y = float(room["y_mm"])
        w = float(room["width_mm"])
        h = float(room["height_mm"])

        poly = rect_to_polygon(x, y, w, h, scale)
        if poly is not None:
            room_polygons.append(poly)
            room_centers.append(room_center(x, y, w, h, scale))
            room_labels.append(room.get("name", room.get("id", "room")))
            room_kinds.append(room.get("kind", "unknown"))

    OUT = (
        boundary,        # 0
        room_polygons,   # 1
        room_centers,    # 2
        room_labels,     # 3
        room_kinds       # 4
    )

except Exception as e:
    OUT = "EXCEPTION: " + str(e) + "\n" + traceback.format_exc()
