import sys
from pathlib import Path

# Das hier muss man hinzufügen, weil er sonst nicht die Module aus anderen Projektordnern findet
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

import Process.process_manager as process_manager


from Agent.tools import erpnext_client as c

print(c.get_list("Item", [], ["name", "item_name"]))
print(c.get_count("Item", []))
print(c.get_doc("Item", "RM-014"))   # ein Item, das du sicher kennst
print(c.get_doc("Item", "gibt-es-nicht"))     # erwartet: None