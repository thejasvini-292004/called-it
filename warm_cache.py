"""Pre-generate every analysis once, so the live demo is instant.

    python warm_cache.py

Writes all 4 bowlers x 5 reasons (including "no reason") = 20 analyses into
analysis_cache.json. The server loads that file at start-up, so any on-time
pick a fan makes is answered straight from the cache. Run it again after
changing the model or the prompt (or delete analysis_cache.json).
"""

import time

from called_it import scenario as sc
from called_it.analyst import Analyst


def main():
    analyst = Analyst()
    info = analyst.info()
    if info["backend"] == "template":
        print("No language model configured (LLM_BACKEND=template), nothing to warm.")
        return
    print(f"Warming analyses with {info['model']} ({info['backend']})...")
    combos = [(p, r) for p in sc.ORDER for r in [None, *sc.REASONS]]
    total = time.time()
    for i, (pick, reason) in enumerate(combos, 1):
        t0 = time.time()
        out = analyst.analyse(pick, reason, True)
        how = "cached" if out.get("cached") else f"{time.time() - t0:.0f}s"
        print(f"[{i:2}/{len(combos)}] {pick:8} {str(reason):8} -> {out['source']:8} ({how})")
    print(f"Done in {time.time() - total:.0f}s. {analyst.info()['cached_analyses']} analyses saved to analysis_cache.json.")


if __name__ == "__main__":
    main()
