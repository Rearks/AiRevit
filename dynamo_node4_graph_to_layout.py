import sys
import importlib

scripts_dir        = str(IN[0])
program_graph_path = str(IN[1])

if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

import layout_generator_v2 as lg
importlib.reload(lg)

OUT = lg.run_single(program_graph_path)
