"""Bind the previously studied seven-class OpenML prediction file; no download."""
import argparse
import json
from pathlib import Path
from .data import digest

OPENML_SHA256 = "8d7d4637968d2ac309531fcbc3ed49414e5d748327cfcdb4ce80b50c90e9fce7"


def prepare(predictions, output):
    predictions, output = Path(predictions).resolve(), Path(output).resolve()
    identity = digest(predictions)
    if identity != OPENML_SHA256:
        raise ValueError("This importer admits only the pinned, previously studied run10160807")
    requests = [dict(kind="quality", a="correct", cutoff=cutoff, numerator=num, denominator=den)
                for cutoff, num, den in ((80,9,10),(80,99,100),(80,99,100),(90,99,100),
                                        (0,9,10),(0,99,100),(101,1,1),(80,99,100))]
    output.mkdir(parents=True, exist_ok=False)
    case = dict(version="0.3-dev", id="openml-confidence-gates", mechanism="quality",
        split="exposed-native-development", history_group="openml-run10160807",
        initial_source=identity, sources={identity:dict(path=str(predictions),
            format="openml-arff-confidence", sha256=identity)},
        tasks=[dict(source_id=identity, request=q) for q in requests],
        provenance=dict(dataset="Covertype 1596", task=75193, run=10160807,
            request_stream="authored; same exposed prediction source, no held-out family",
            full_observation="complete correctness/confidence contingency table, not raw ARFF retention"))
    path = output / "quality.case.json"
    path.write_text(json.dumps(case, indent=2) + "\n", encoding="utf-8")
    return str(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(prepare(args.predictions, args.output))
