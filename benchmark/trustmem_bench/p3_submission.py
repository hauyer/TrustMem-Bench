"""Prepare single-track P3 cases, run an external predictor, or score its JSONL."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile


PREFIX = "artifacts/research_decisions/20261120-p3-prospective-audit-increment-v1/"
MEMBERS = {
    "OBSERVE_LOSS.json": "91cf5bde5fe39a0d540412810666bd3dd5d6fc8faafc2b56cc0fcc5a0bf1ff19",
    "RESULT.json": "4f50bd91a409ce9a30d298ed85ba21a1ed0bb5e57ff122c3f61591cd04b68f71",
    "ADMISSION_AUDIT.json": "f08e32b89cbd2b44b17b6a68ed4512c104c87b5ba74cf6c9f906c566a5871ded",
}
OBSERVED_FIELDS = (
    "workflow", "day", "mode", "public_task", "public_pricing", "targets", "scope",
    "focal_key", "initial_budget", "remaining", "calls", "dispatch", "completed",
    "published", "post_publish_confirmed", "blocked_optional_post_publish_price",
    "same_value_read", "same_value_cost", "focal_reread_different",
    "focal_prior_rejected", "focal_receipt_used_in_loss",
)
LABELS = {
    "business_omission", "fewer_business_completions", "target_swap",
    "confirmation_only", "no_terminal_change", "undecided",
}


def member(archive, name):
    data = archive.read(PREFIX + name)
    if sha256(data).hexdigest() != MEMBERS[name]:
        raise ValueError(f"RC6 member differs from the sealed study: {name}")
    return json.loads(data)


def case_id(row):
    return f"{row['workflow']}-T{row['day']:02}-{row['mode']}"


def public_cases(archive):
    cases = []
    for row in member(archive, "OBSERVE_LOSS.json"):
        if row["status"] == "eligible":
            questions = ["total"] if row["same_value_read"] is None else ["total", "fee"]
            cases.append(dict(case_id=case_id(row), questions=questions,
                              observation={k: row[k] for k in OBSERVED_FIELDS}))
    return cases


def unique_fields(pairs):
    obj = {}
    for name, value in pairs:
        if name in obj:
            raise ValueError(f"Duplicate JSON field: {name}")
        obj[name] = value
    return obj


def read_records(path):
    records = []
    with path.open(encoding="utf-8-sig") as stream:
        for i, line in enumerate(stream, start=1):
            try:
                records.append(json.loads(line, object_pairs_hook=unique_fields))
            except ValueError as err:
                raise ValueError(f"{path.name} line {i}: {err}") from err
    return records


def write_file(path, content):
    with path.open("x", encoding="utf8", newline="\n") as stream:
        stream.write(content)


def json_lines(rows):
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)


def check_answers(case, answers):
    identifier = case["case_id"]
    if not isinstance(answers, dict) or set(answers) != set(case["questions"]):
        raise ValueError(f"{identifier}: supply exactly the listed questions")
    targets = set(case["observation"]["targets"])
    for question, value in answers.items():
        if not isinstance(value, dict) or set(value) != {"label", "added", "displaced"}:
            raise ValueError(f"{identifier}/{question}: expected label, added and displaced")
        if not isinstance(value["label"], str) or value["label"] not in LABELS:
            raise ValueError(f"{identifier}/{question}: unknown label")
        for field in ("added", "displaced"):
            ids = value[field]
            if (not isinstance(ids, list) or not all(isinstance(t, str) for t in ids)
                    or len(set(ids)) != len(ids) or not set(ids) <= targets):
                raise ValueError(f"{identifier}/{question}: invalid {field} targets")
        if set(value["added"]) & set(value["displaced"]):
            raise ValueError(f"{identifier}/{question}: overlapping target sets")
        if value["label"] == "undecided" and (value["added"] or value["displaced"]):
            raise ValueError(f"{identifier}/{question}: abstention must have empty target sets")


def run_predictor(cases, predictor):
    predictor = predictor.resolve(strict=True)
    predictions = []
    for case in cases:
        with TemporaryDirectory() as work:
            result = subprocess.run(
                [sys.executable, "-B", "-X", "utf8", str(predictor)],
                input=json.dumps(case), text=True, encoding="utf8", capture_output=True, cwd=work,
            )
        if result.returncode:
            raise ValueError(f"{case['case_id']}: predictor exited {result.returncode}: {result.stderr.strip()}")
        answers = json.loads(result.stdout, object_pairs_hook=unique_fields)
        check_answers(case, answers)
        predictions.append(dict(case_id=case["case_id"], answers=answers))
    return predictions


def tally(stats, answer, gold, calls):
    label = answer["label"]
    decided = label != "undecided"
    correct_class = label == gold["predicted_class"]
    exact = (correct_class and set(answer["added"]) == set(gold["predicted_added_targets"])
             and set(answer["displaced"]) == set(gold["predicted_displaced_targets"]))
    stats.update(cells=1, class_correct=correct_class, exact_correct=exact,
                 decided=decided, abstained=not decided, decided_wrong=decided and not exact,
                 exact_after_replaying_abstentions=exact or not decided,
                 full_replay_calls=calls, replay_calls_on_abstentions=0 if decided else calls)


def score(archive, submissions):
    cases = {c["case_id"]: c for c in public_cases(archive)}
    outcomes = {case_id(r): r for r in member(archive, "RESULT.json")["rows"] if r["status"] == "eligible"}
    if cases.keys() != outcomes.keys():
        raise ValueError("Frozen observation and outcome cohorts differ")
    admission = member(archive, "ADMISSION_AUDIT.json")
    released = {r["workflow"] for r in admission["rescope"]
                if r["formal_binding"]["activation_status"] == "released"
                and r["formal_binding"]["formal_launch_authorized"]}
    seen = set()
    cohort_names = {"all_five", "released_four"} | {r["workflow"] for r in outcomes.values()}
    groups = {(name, mode, q): Counter(cells=0, class_correct=0, exact_correct=0, decided=0,
                                       abstained=0, decided_wrong=0, exact_after_replaying_abstentions=0,
                                       full_replay_calls=0, replay_calls_on_abstentions=0)
              for name in cohort_names for mode in ("ALL", "ordered", "low_cost") for q in ("total", "fee")}
    for submitted in submissions:
        if not isinstance(submitted, dict) or set(submitted) != {"case_id", "answers"}:
            raise ValueError("Each submission row needs case_id and answers")
        identifier = submitted["case_id"]
        if not isinstance(identifier, str) or identifier not in cases or identifier in seen:
            raise ValueError(f"Unknown or duplicate case: {identifier}")
        seen.add(identifier)
        case, row = cases[identifier], outcomes[identifier]
        if set(case["questions"]) != {q for q in ("total", "fee") if row[q] is not None}:
            raise ValueError(f"{identifier}: frozen observation and scored questions differ")
        check_answers(case, submitted["answers"])
        cohorts = ["all_five", row["workflow"]]
        if row["workflow"] in released:
            cohorts.append("released_four")
        for question, answer in submitted["answers"].items():
            arm = "archive" if question == "total" else "fee_only"
            gold = row[question]
            calls = row["costs"][arm]["calls"]
            for cohort in cohorts:
                for mode in ("ALL", row["mode"]):
                    tally(groups[cohort, mode, question], answer, gold, calls)
    if seen != cases.keys():
        raise ValueError(f"Missing {len(cases.keys() - seen)} cases")
    results = []
    for (cohort, mode, question), stats in sorted(groups.items()):
        n = stats["cells"]
        saved = stats["full_replay_calls"] - stats["replay_calls_on_abstentions"]
        results.append(dict(cohort=cohort, mode=mode, question=question, **stats,
                            exact_accuracy=stats["exact_correct"] / n if n else None,
                            coverage=stats["decided"] / n if n else None, replay_calls_saved=saved))
    return dict(study="TrustMem-Bench P3 RC6", cases=len(seen), results=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="command", required=True)
    export = modes.add_parser("export", help="export the observed loss track only")
    run = modes.add_parser("run", help="send one observation at a time to a Python predictor")
    grade = modes.add_parser("score", help="score a complete external JSONL submission")
    for cmd in (export, grade):
        cmd.add_argument("--archive", type=Path, required=True)
    run.add_argument("--cases", type=Path, required=True)
    run.add_argument("--predictor", type=Path, required=True)
    grade.add_argument("--predictions", type=Path, required=True)
    for cmd in (export, run, grade):
        cmd.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error(f"Output already exists: {args.out}")
    if args.command == "run":
        content = json_lines(run_predictor(read_records(args.cases), args.predictor))
    else:
        with ZipFile(args.archive) as archive:
            if args.command == "export":
                content = json_lines(public_cases(archive))
            else:
                content = json.dumps(score(archive, read_records(args.predictions)), indent=2) + "\n"
    write_file(args.out, content)


if __name__ == "__main__":
    main()
