import sys
import importlib

scripts_dir = str(IN[0])
prompt      = str(IN[1])

if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

import prompt_to_program_graph as p2g
importlib.reload(p2g)

OUT = p2g.run_from_dynamo(prompt)
