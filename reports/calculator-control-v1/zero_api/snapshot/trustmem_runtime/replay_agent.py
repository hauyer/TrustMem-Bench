"""Replay saved decisions exactly. This is not a new autonomous model run."""
import json
from pathlib import Path
import sys


if __name__ == "__main__":
    plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    observation = json.loads(sys.stdin.readline())
    if observation["phase"] == "bootstrap":
        action = plan["bootstrap"]
    else:
        action = plan["tasks"][observation["session_index"]][len(observation["trace"])]
    print(json.dumps(action))
