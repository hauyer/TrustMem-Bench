"""Bind already downloaded native public archives; no network or redistribution."""
import argparse
import json
from pathlib import Path
from .data import digest, scan


SOURCES = {
    "gh-0601":("gharchive","2fd1904e1d9107d11473f869e4dffe20926d0f41fc9dd50e49bf3404c70dbb32","https://data.gharchive.org/2024-06-01-0.json.gz"),
    "gh-0602":("gharchive","32f94b9e40d8845c8f124bb3e87f099ba0fe04a069c00a2f5c3c1378ea9d6330","https://data.gharchive.org/2024-06-02-0.json.gz"),
    "wiki-0601":("wikimedia","d6538621cae195c5e0674a0972d709e2086e6a3398abf24c749b29ed1e160028","https://dumps.wikimedia.org/other/pageviews/2024/2024-06/pageviews-20240601-000000.gz"),
    "wiki-0602":("wikimedia","5e807740da5a25c85ea8f0d4f6471e819370401da2232f8272ef8a4b03b2f9f5","https://dumps.wikimedia.org/other/pageviews/2024/2024-06/pageviews-20240602-000000.gz"),
}


def prepare(data_dir, output):
    data_dir, output = Path(data_dir).resolve(), Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    sources, margins = {}, {}
    for label,(fmt,identity,url) in SOURCES.items():
        path = data_dir/f"{label}.gz"
        if digest(path) != identity:
            raise ValueError(f"Wrong source: {label}")
        source = {"format":fmt,"path":str(path),"sha256":identity,"url":url}
        table, cost = scan(source)
        left, right = {}, {}
        for a,cells in table.items():
            left[a] = sum(cells.values())
            for b,value in cells.items():
                right[b] = right.get(b,0)+value
        # Group early stop is deliberately disabled unless layout is certified.
        # Current Wikimedia admission uses an independent order-only pass.
        if fmt == "wikimedia":
            import gzip
            seen, last, contiguous = set(),None,True
            with gzip.open(path,"rb") as stream:
                for line in stream:
                    domain = line.split(b" ",1)[0]
                    if domain != last:
                        contiguous &= domain not in seen
                        seen.add(domain)
                        last = domain
            source["group_contiguous"] = contiguous
        margins[label] = (left,right)
        sources[label] = source
        print(json.dumps({"admitted":label,"bytes":path.stat().st_size,"group_contiguous":source.get("group_contiguous",False)}),flush=True)
    for family in ("gh","wiki"):
        first, second = f"{family}-0601",f"{family}-0602"
        left,right = margins[first]
        ranked_a = sorted(left,key=lambda k:(-left[k],k))
        ranked_b = sorted(right,key=lambda k:(-right[k],k))
        a1,a2,b = ranked_a[0],ranked_a[1],ranked_b[0]
        absent = "__trustmem_absent_group__"
        if absent in right:
            raise ValueError("Absent control unexpectedly present")
        queries = [{"kind":"marginal","a":a1},{"kind":"joint","a":a1,"b":absent}]
        queries += [{"kind":"joint","a":a1,"b":b} for _ in range(4)]
        queries += [{"kind":"joint","a":a2,"b":b},{"kind":"joint","a":a1,"b":b}]
        identities = [sources[first]["sha256"],sources[second]["sha256"]]
        case = {"version":"0.2-dev","id":f"native-{family}","mechanism":"cross","split":"previously-seen-native-development",
            "history_group":family,"initial_source":identities[0],"sources":{sources[k]["sha256"]:sources[k] for k in (first,second)},
            "tasks":[{"source_id":identities[v],"request":q} for q,v in zip(queries,(0,0,0,0,1,1,1,0))]}
        (output/f"{family}.case.json").write_text(json.dumps(case,indent=2)+"\n",encoding="utf-8")
    (output/"admission.json").write_text(json.dumps({"source_files":sources,"query_selection":"Initial marginal rank only; no joint-value or policy-result selection.",
        "preparation_is_common":True,"not_in_policy_runtime_cost":True,"redistributed_source_data":False},indent=2)+"\n",encoding="utf-8")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir",required=True)
    p.add_argument("--output",required=True)
    args = p.parse_args()
    prepare(args.data_dir,args.output)
