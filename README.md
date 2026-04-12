<p align="center">
  <img src="https://img.shields.io/badge/Revit-2023%2B-0066CC?logo=autodesk" alt="Revit Version">
  <img src="https://img.shields.io/badge/Dynamo-2.x-orange" alt="Dynamo">
  <img src="https://img.shields.io/badge/Python-3.x-3776AB?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/LLM%20Required-None-brightgreen" alt="No LLM">
  <img src="https://img.shields.io/badge/Hallucinations-Zero-brightgreen" alt="Zero Hallucinations">
  <img src="https://img.shields.io/badge/Status-Beta-blueviolet" alt="Status">
</p>

# 🏗️ AiRevit: Text-to-BIM — Zero Hallucination Generative Engine

> **Most "AI in BIM" tools are just LLM wrappers with unpredictable outputs.**  
> AiRevit takes a fundamentally different approach.

**AiRevit** is a fully deterministic, data-driven pipeline that converts natural language architectural briefs into optimized floor layouts and deploys them directly as 3D BIM elements in Autodesk Revit — **without a single LLM call**, without unpredictable outputs, and with zero hallucinations.

---

## 🧠 The Core Philosophy: Rules over Hallucinations

The generative AI hype has a serious problem in AEC: **LLMs do not understand architectural constraints.**  
They will happily generate a toilet inside a load-bearing structural core, or propose a 3m² office as "suitable for 10 people."

AiRevit instead uses a **hard-coded semantic vocabulary parser + graph-based layout solver**, preparing for a future **Graph Neural Network (GNN)** engine trained on a growing, structured dataset. The result:

- ✅ **Zero hallucinations** — every output follows strict topological rules
- ✅ **Fully auditable** — every decision in the pipeline is traceable
- ✅ **Offline-capable** — no API keys, no network calls, no cloud dependency
- ✅ **Open dataset** — you contribute to the training data simply by using it

---

## ⚙️ How The Pipeline Works

```
Natural Language Prompt
        │
        ▼ (prompt_to_program_graph.py + vocabulary.json)
        │  ► Deterministic NLP parser, NO LLM
        │  ► Extracts: space types, counts, areas, ratios, constraints
        │  ► Validates topology: connections, flows, adjacency rules
        │
 program_graph.json  (v2.0 schema)
        │
        ▼ (layout_generator_v2.py)
        │  ► Algorithmic solver with spatial templates
        │  ► Resolves physical dimensions from constraints
        │  ► Ensures: corridor adjacency, wet-zone isolation, daylight access
        │
 layout_solution.json
        │
        └──► node8_create_revit_elements.py ──► Revit walls + doors + room labels
```

---

## ⚡ Quick Start: Running entirely in Dynamo

This pipeline is designed to be run from start to finish directly inside **Dynamo** (Revit 2023 / 2024+).

### The Node Setup (Building the Graph)

**Node 1 — The Prompt**
* Use a `String` node. Enter your prompt here: *"Design an office: corridor, two workrooms, meeting room, WC."*

**Node 2 — The Scripts Folder**
* Use a `File Path` node pointing to the directory where you cloned `AiRevit`.

**Node 3 — Parse Prompt to Graph**
* Use a `Python Script` node. Paste this code:
```python
import sys
import importlib

scripts_dir = str(IN[0])   # File Path -> папка со скриптами
prompt      = str(IN[1])   # String -> промт

if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

# Reload to ensure we have the latest version if edited
import prompt_to_program_graph as p2g
importlib.reload(p2g)

result_path = p2g.run_from_dynamo(prompt)
OUT = result_path
```

**Node 4 — Generate Layout**
* Use a `Python Script` node. Connect the `OUT` from Node 3 to `IN[1]`.
```python
import sys
import importlib

scripts_dir        = str(IN[0])   # File Path -> папка со скриптами
program_graph_path = str(IN[1])   # Путь к graph JSON из Node 3

if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

import layout_generator_v2 as lg
importlib.reload(lg)

layout_path = lg.run_single(program_graph_path)
OUT = layout_path
```

**Node 5 & 6 — Create Revit Elements**
* Optional: Add a `File Path` node using the string output from Node 4. (Or connect directly).
* Use a `Python Script` node and paste the entire contents of `node8_create_revit_elements.py`. Connect `IN[0]` to the output of Node 4.

Hit **Run** in Dynamo, and the walls, doors, and rooms will instantly appear in your active Revit view!

---

## 🗂️ Repository Structure

```
AiRevit/
├── prompt_to_program_graph.py     # Stage 1: NLP parser → JSON graph
├── vocabulary.json                # Controlled vocabulary (space synonyms etc)
├── design_rules.json              # Spatial constraints (must be in root folder)
├── layout_generator_v2.py         # Stage 2: Algorithmic layout solver
├── node8_create_revit_elements.py # Dynamo: Revit wall/door/room creation
└── dataset/
    ├── generated_program_graphs/  # Auto-generated program graph JSONs
    └── layout_solutions_v2/       # Solved layout JSONs (ready for Revit)
```

---

## 🗺️ Roadmap

### v1.0 — Current (Beta)
- [x] Deterministic NLP prompt parser with `vocabulary.json`
- [x] Graph-based program graph schema (v2.0)
- [x] Multi-template layout solver (`left_service_stack`, `single_room`)
- [x] Revit element creation (walls, doors, room labels) via Dynamo (Revit 2024+ compatible)
- [x] Growing dataset in `dataset/` for future GNN training

### v2.0 — Next (Planned)
- [ ] **GNN-based layout optimization** trained on the accumulated dataset
- [ ] More spatial templates (`central_corridor`, `open_plan`, `L-shape`)
- [ ] Automated door placement from connection graph
- [ ] Multi-floor layout support

### v3.0 — The Open Vision 🌍
- [ ] **Complete pivot to Blender + [Bonsai BIM addon](https://bonsaibim.org/)** (formerly BlenderBIM)
- [ ] Fully IFC-native output — no proprietary software required
- [ ] Community-driven vocabulary and template dataset

---

## 🤝 Contributing

This project lives and grows through contributions. Here is how you can help right now:
1. **Try it and report issues** — even bug reports with your prompt and output JSON are invaluable
2. **Add vocabulary** — edit `vocabulary.json` to add synonyms for your language or domain
3. **Contribute layouts** — drop your real floor plan as an annotated JSON into `dataset/`

---

## 📄 License
MIT — free to use, modify, and distribute.
