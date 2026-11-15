"""Read a tick recording (even one still being written)."""
import gzip, json, glob
def read(path=None):
    path = path or sorted(glob.glob("data/ticks/ticks_*.jsonl.gz"))[-1]
    rows = []
    try:
        with gzip.open(path, "rt") as f:
            for l in f:
                try: rows.append(json.loads(l))
                except ValueError: break
    except EOFError:
        pass
    return rows
