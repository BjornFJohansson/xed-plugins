#!/home/bjorn/.pyenv/versions/pydna312_bp185/bin/python

# important!
# 1. Change the shebang above to a python interpreter with Pydna installed
# 2. Make this script executable


import sys
import json
from pydna.dseqrecord import Dseqrecord

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue

    req = json.loads(line)
    cmd = req.get("cmd")

    if cmd == "shutdown":
        print(json.dumps({"ok": True}), flush=True)
        break

    try:
        if cmd == "reverse_complement":
            seq = req["sequence"]
            rec = Dseqrecord(seq)
            result = str(rec.reverse_complement().seq)
            print(json.dumps({"ok": True, "result": result}), flush=True)

        elif cmd == "format":
            seq = req["sequence"]
            fmt = req.get("format", "genbank")
            rec = Dseqrecord(seq)
            result = rec.format(fmt)
            print(json.dumps({"ok": True, "result": result}), flush=True)

        else:
            print(json.dumps({"ok": False, "error": f"unknown command: {cmd}"}), flush=True)

    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}), flush=True)
