"""Ordinary D1 entry-threshold baseline for one external P3 case on stdin."""
import json
import sys


def predict(case):
    observed = case["observation"]
    index = observed["same_value_read"]
    added = []
    if index is not None:
        for step in observed["dispatch"]:
            if (step["stop"] == "unfunded_entry" and step["start"] > index
                    and step["floor"] <= step["balance"] + observed["same_value_cost"]):
                added = [step["target"]]
                break
    label = "business_omission" if added else "no_terminal_change"
    return {q: dict(label=label, added=added, displaced=[]) for q in case["questions"]}


if __name__ == "__main__":
    print(json.dumps(predict(json.load(sys.stdin))))
