"""Executable ordinary policies. Each invocation is a fresh process."""
import json
import sys


def decide(observation, policy):
    if observation["phase"] == "bootstrap":
        return {"action":"capture_full" if policy == "eager_full" else "start"}
    trace = observation["trace"]
    last = trace[-1] if trace else None
    if last and last["result"].get("value") is not None:
        result = last["result"]
        if last["action"]["action"] == "query" and policy in ("lazy_group","lazy_full","eager_full"):
            return {"action":"save","receipt_id":result["receipt_id"]}
        return {"action":"submit","value":result["value"],"evidence":result["evidence"]}
    if last and last["action"]["action"] == "save":
        before = trace[-2]["result"]
        return {"action":"submit","value":before["value"],"evidence":before["evidence"]}
    if policy == "always_verify":
        return {"action":"query","scope":"full"}
    # All policies share the same public calculator; no policy sees SQL gold.
    if not trace:
        return {"action":"calculate","evidence":["history"]+[m["id"] for m in observation["memory"]]}
    if observation["request"]["kind"] == "quality" and observation["history"]["source_id"] != observation["source_id"]:
        # A group result alone does not supply the selected population denominator.
        return {"action":"query","scope":"full"}
    return {"action":"query","scope":"full" if policy in ("lazy_full","eager_full") else "group"}


if __name__ == "__main__":
    observation = json.loads(sys.stdin.readline())
    print(json.dumps(decide(observation, sys.argv[1])))
