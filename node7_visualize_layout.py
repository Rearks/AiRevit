import clr
import json

clr.AddReference('ProtoGeometry')
from Autodesk.DesignScript.Geometry import Point, Polygon, Line

clr.AddReference('DSCoreNodes')
from DSCore import Color

def get_color(kind):
    k = (kind or "").lower()
    if k == "corridor":
        return Color.ByARGB(255, 128, 128, 128) # серый
    elif k == "office":
        return Color.ByARGB(255, 0, 0, 255) # синий
    elif k == "wc":
        return Color.ByARGB(255, 255, 0, 0) # красный
    return Color.ByARGB(255, 200, 200, 200) # по умолчанию

# IN[0] = путь к layout_solution.json
# IN[1] = scale, например 0.001 (мм -> м)

file_path = IN[0]

try:
    if len(IN) > 1 and IN[1] is not None:
        scale = float(IN[1])
        if scale <= 0:
            scale = 0.001
    else:
        scale = 0.001
except:
    scale = 0.001

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

def door_to_line(door, s=1.0):
    x = door.get("x_mm", 0)
    y = door.get("y_mm", 0)
    width = door.get("width_mm", 0)
    if width <= 0:
        return None
    orientation = door.get("orientation", "vertical")

    if orientation == "vertical":
        p1 = Point.ByCoordinates(x * s, y * s, 0)
        p2 = Point.ByCoordinates(x * s, (y + width) * s, 0)
    else:
        p1 = Point.ByCoordinates(x * s, y * s, 0)
        p2 = Point.ByCoordinates((x + width) * s, y * s, 0)

    try:
        return Line.ByStartPointEndPoint(p1, p2)
    except:
        return None

# Boundary
boundary_data = data.get("boundary", {})
boundary = None
b_x = float(boundary_data.get("x_mm", 0))
b_y = float(boundary_data.get("y_mm", 0))
b_w = float(boundary_data.get("width_mm", 0))
b_h = float(boundary_data.get("height_mm", 0))

if b_w > 0 and b_h > 0:
    try:
        boundary = rect_to_polygon(b_x, b_y, b_w, b_h, scale)
    except:
        boundary = None

# Rooms
room_polygons = []
room_labels = []
room_centers = []
room_kinds = []
room_ids = []
room_colors = []

for room in data.get("rooms", []):
    x = room["x_mm"]
    y = room["y_mm"]
    w = room["width_mm"]
    h = room["height_mm"]

    poly = rect_to_polygon(x, y, w, h, scale)
    center = room_center(x, y, w, h, scale)

    room_polygons.append(poly)
    room_centers.append(center)
    room_labels.append(room.get("name", room.get("id", "room")))
    room_kinds.append(room.get("kind", "unknown"))
    room_ids.append(room.get("id", "unknown"))
    room_colors.append(get_color(room.get("kind", "unknown")))

# Doors
door_lines = []
door_ids = []

for op in data.get("openings", []):
    try:
        line = door_to_line(op, scale)
        door_lines.append(line)
        door_ids.append(op.get("id", "door"))
    except:
        pass

OUT = (
    boundary,        # 0
    room_polygons,   # 1
    room_centers,    # 2
    room_labels,     # 3
    room_kinds,      # 4
    room_ids,        # 5
    door_lines,      # 6
    door_ids,        # 7
    room_colors      # 8
)
