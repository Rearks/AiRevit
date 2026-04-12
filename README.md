<p align="center">
  <img src="https://img.shields.io/badge/Revit-2023%2B-blue" alt="Revit Version">
  <img src="https://img.shields.io/badge/Python-3.x-green" alt="Python">
  <img src="https://img.shields.io/badge/Dynamo-2.x-orange" alt="Dynamo">
  <img src="https://img.shields.io/badge/Status-Beta-purple" alt="Status">
</p>

# 🏗️ AiRevit: Text-to-BIM Generative Engine

**AiRevit** is an open-source generative design pipeline that converts natural language prompts directly into structured, optimized floor layouts and generates 3D BIM elements in Autodesk Revit. 

Say goodbye to manual drafting. Just describe your requirements, and the AI will define the topology, optimize the layout, and deploy it to your BIM view.

> ***"Design an office: corridor, two large workspaces, a meeting room, and a restroom. Total area 100m²."***
> **→ Fully generated Revit walls, doors, and rooms in seconds.**

---

## 🌟 Why AiRevit?

Currently, generative design and AI in the AEC (Architecture, Engineering, Construction) sector are largely locked behind closed, proprietary platforms. **AiRevit aims to break this monopoly.**

By providing a transparent, hackable, and completely open-source pipeline, we aim to offer the AEC community both the "fish" (working layouts) and the "fishing rod" (a complete dataset generator and LLM evaluation pipeline).

### 🚀 Future Roadmap: The fully open ecosystem
While our current execution engine lives inside Dynamo/Revit, **our next major leap is a complete pivot to an open-source ecosystem.** 

In upcoming versions, AiRevit will export directly to **Blender** using the **Bonsai BIM addon** (formerly BlenderBIM). 
This means true open-source generative BIM (IFC-native) without expensive proprietary licenses!

---

## 🛠️ The Pipeline Architecture (v2)

Our pipeline strictly separates cognitive parsing from physical BIM execution:

1. **Prompt to Topology (`prompt_to_program_graph.py`)**
   Uses an LLM (via OpenRouter) to semantically parse natural language into a strict JSON program graph showing rooms, requirements, and constraints.
   
2. **Layout Optimization (`layout_generator_v2.py`)**
   A deterministic algorithmic solver that takes the graph and generates physical dimensions, coordinates, and boundaries (`layout_solution.json`) based on specific spatial templates.
   
3. **BIM Visualizer (`node7_visualize_layout.py`)**
   A lightweight Dynamo node to preview generated polygons and orientations in 3D space safely.
   
4. **Revit Execution (`node8_create_revit_elements.py`)**
   The final engine that parses the layout JSON, automatically resolves wall families, places doors, and generates rooms with programmatic Area Tags inside Revit.

---

## ⚡ Quick Start

### 1. Generate the Layout
Make sure you have your OpenRouter API key ready. Run the prompt parser:
```bash
python prompt_to_program_graph.py "Create a 50x50 sqft private office space"
```
This generates a graph in `dataset/generated_program_graphs/`.

Next, run the layout engine to resolve geometry:
```bash
python layout_generator_v2.py
```
This drops the final coordinates into `dataset/layout_solutions_v2/`.

### 2. Execute in Dynamo (Revit 2023 / 2024+)
1. Open Revit and launch **Dynamo**.
2. Create a `File Path` node and point it to your new `layout_solution.json`.
3. Create a `Python Script` node and paste the contents of `node8_create_revit_elements.py`.
4. Connect `File Path` to `IN[0]`.
5. Press **Run**! The walls, internal doors, and room labels will instantly appear in your active view.

---

## 🤝 Contributing

This project is in its early stages. We have achieved end-to-end functionality, but we need the community's help to grow the spatial templates, improve the graph resolution algorithms, and prepare for the Blender/Bonsai pivot.

Feel free to fork the repository, try generating layouts, and submit Pull Requests! Let's build the future of Open BIM AI together.
