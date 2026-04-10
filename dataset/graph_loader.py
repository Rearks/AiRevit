import json
import glob
import os

def load_graph(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    spaces = data.get("spaces", [])
    connections = data.get("connections", [])
    flows = data.get("flows", [])
    
    kinds = [s.get("kind", "unknown") for s in spaces]
    
    total_area = 0.0
    for s in spaces:
        area = s.get("area_m2")
        if area is not None:
            total_area += float(area)
            
    pattern = "-".join(kinds)
    
    return {
        "filename": os.path.basename(filepath),
        "spaces_count": len(spaces),
        "connections_count": len(connections),
        "kinds": kinds,
        "total_area": total_area,
        "flows_count": len(flows),
        "pattern": pattern,
        "data": data # if needed for other scripts
    }

def print_stats(g_info):
    print(g_info["filename"])
    print(f"spaces: {g_info['spaces_count']}")
    print(f"connections: {g_info['connections_count']}")
    print(f"space kinds: {', '.join(g_info['kinds'])}")
    print(f"total area: {g_info['total_area']:.2f}")
    print(f"pattern: {g_info['pattern']}")
    print(f"flows: {g_info['flows_count']}")
    print("-" * 30)

def main():
    directory = r"c:\Users\kraer\AiRevit\dataset\annotations"
    files = glob.glob(os.path.join(directory, "office*.json"))
    
    for f in list(files)[:20]:
        g_info = load_graph(f)
        print_stats(g_info)

if __name__ == "__main__":
    main()
