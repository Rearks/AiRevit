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
        ├──► node7_visualize_layout.py  ──► Dynamo 3D polygon preview
        │
        └──► node8_create_revit_elements.py ──► Revit walls + doors + room labels
```

---

## ⚡ Quick Start

**Prerequisites:** Python 3.x, Autodesk Revit 2023+, Dynamo 2.x

### Step 1 — Parse your prompt to a graph

```bash
python prompt_to_program_graph.py
```

Edit the `test_prompts` list in `main()` or call `parse_prompt()` directly:

```python
from prompt_to_program_graph import parse_prompt
graph = parse_prompt("Design an office: corridor, 2 workrooms, meeting room, WC. Total area 120 m².")
```

→ Saves to `dataset/generated_program_graphs/prompt_<id>.json`

### Step 2 — Generate the layout

```bash
python layout_generator_v2.py
```

→ Saves optimized coordinates to `dataset/layout_solutions_v2/prompt_<id>_layout_v2.json`

### Step 3 — Deploy to Revit via Dynamo

1. Open Revit, launch **Dynamo**.
2. Add a **`File Path`** node → point to your `layout_solution.json`.
3. Add a **`Python Script`** node → paste contents of `node8_create_revit_elements.py`.
4. Add a **`Watch`** node to the output.
5. Connect `File Path → IN[0]`, press **Run**.

✅ Walls, internal doors, and room labels will appear in your Revit view.

---

## 🗂️ Repository Structure

```
AiRevit/
├── prompt_to_program_graph.py     # Stage 1: NLP parser → program_graph.json
├── vocabulary.json                # Controlled vocabulary (space synonyms, quantities, units)
├── layout_generator_v2.py         # Stage 2: Algorithmic layout solver
├── node7_visualize_layout.py      # Dynamo: 3D polygon preview
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
- [x] Dynamo visualization node (CPython3 compatible)
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
- [ ] Web-based layout annotation tool for crowdsourcing the training dataset

---

## 🤝 Contributing

This project lives and grows through contributions. Here is how you can help right now:

1. **Try it and report issues** — even bug reports with your prompt and output JSON are invaluable
2. **Add vocabulary** — edit `vocabulary.json` to add synonyms for your language or domain
3. **Contribute layouts** — drop your real floor plan as an annotated JSON into `dataset/`
4. **Add templates** — implement a new spatial template in `layout_generator_v2.py`

---

## 📄 License

MIT — free to use, modify, and distribute.

---

<p align="center">
  <b>Built for the AEC open-source community.</b><br>
  If this helped you, please star ⭐ the repo — it helps others discover it.
</p>
