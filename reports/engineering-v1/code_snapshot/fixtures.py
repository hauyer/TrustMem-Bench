"""Small, deterministic engineering fixtures; these are not held-out research data."""
import argparse
import json
from pathlib import Path
from .data import canonical, digest


def build(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    definitions = {
        "cross": [{"red": {"north":3,"south":2},"blue":{"north":1,"south":4}},
                  {"red":{"north":1,"south":5},"blue":{"north":4,"south":2}}],
        "threshold": [{"red":{"10":3,"20":2,"30":1},"blue":{"10":2,"20":1,"30":4}},
                      {"red":{"10":1,"20":2,"30":4},"blue":{"10":3,"20":2,"30":2}}],
        "range": [{"red":{"1":10,"2":-3,"3":5,"4":7},"blue":{"1":2,"2":9,"3":-1,"4":4}},
                  {"red":{"1":9,"2":-1,"3":3,"4":2},"blue":{"1":5,"2":4,"3":-2,"4":8}}],
    }
    manifests = []
    for mechanism, tables in definitions.items():
        sources, identities = {}, []
        for version, table in enumerate(tables):
            path = output / f"{mechanism}-{version}.jsonl"
            path.write_text("".join(canonical({"a":a,"b":b,"weight":w})+"\n" for a,cells in table.items() for b,w in cells.items()), encoding="utf-8")
            identity = digest(path)
            identities.append(identity)
            sources[identity] = {"path":path.name,"format":"weighted-jsonl","sha256":identity}
        if mechanism == "cross":
            queries = [{"kind":"marginal","a":"red"}, {"kind":"joint","a":"red","b":"absent"},
                {"kind":"joint","a":"red","b":"north"}, {"kind":"joint","a":"red","b":"north"},
                {"kind":"joint","a":"red","b":"north"}, {"kind":"joint","a":"red","b":"north"},
                {"kind":"joint","a":"blue","b":"north"}, {"kind":"joint","a":"red","b":"north"}]
        elif mechanism == "threshold":
            queries = [{"kind":"marginal","a":"red"}, {"kind":"threshold","a":"red","limit":-1}]
            queries += [{"kind":"threshold","a":"red","limit":n} for n in (20,25,20,20)]
            queries += [{"kind":"threshold","a":"blue","limit":10}, {"kind":"threshold","a":"red","limit":25}]
        else:
            queries = [{"kind":"range","a":"red","lo":1,"hi":n} for n in (2,3,4,4,4,4)]
            queries += [{"kind":"range","a":"blue","lo":1,"hi":2}, {"kind":"range","a":"red","lo":1,"hi":4}]
        tasks = [{"source_id":identities[version],"request":query} for query,version in zip(queries,(0,0,0,0,1,1,1,0))]
        case = {"version":"0.2-dev","id":f"engineering-{mechanism}","mechanism":mechanism,
            "split":"engineering-smoke","history_group":f"synthetic-{mechanism}",
            "initial_source":identities[0],"sources":sources,"tasks":tasks}
        path = output / f"{mechanism}.case.json"
        path.write_text(json.dumps(case, indent=2)+"\n", encoding="utf-8")
        manifests.append(str(path))
    return manifests


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    print(json.dumps(build(parser.parse_args().output), indent=2))
