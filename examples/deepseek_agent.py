"""Optional sequential paid adapter. Requires explicit caps and environment key."""
import argparse
import json
import math
from pathlib import Path
import sys
from metered_deepseek import DeepSeekClient


SYSTEM = ('Act as an agent using the documented tools. Return one JSON action object only. '
          'Follow the source, evidence, memory and tool contracts in the observation. '
          'Minimize unnecessary source reads while completing the requested tasks correctly; '
          'decide what to retain without knowing future requests. '
          'The action field must be a string in a FLAT JSON object. Valid shapes are '
          '{"action":"start"}, {"action":"capture_full"}, '
          '{"action":"calculate","evidence":["history"]}, '
          '{"action":"query","scope":"group"}, '
          '{"action":"save","receipt_id":"ID"}, '
          '{"action":"submit","value":0,"evidence":["ID"]}, or '
          '{"action":"abstain"}. Do not wrap the object inside type, tool, arguments, or another action object.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-dir",required=True)
    parser.add_argument("--max-usd",required=True,type=float)
    parser.add_argument("--max-calls",required=True,type=int)
    args = parser.parse_args()
    if not math.isfinite(args.max_usd) or args.max_usd <= 0 or args.max_calls <= 0:
        parser.error("Positive finite limits are required")
    ledger = Path(args.ledger_dir).resolve()
    ledger.mkdir(parents=True,exist_ok=True)
    if (ledger/"STOP.json").exists():
        return 1
    log = ledger/"model_calls.jsonl"
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    spent = sum(row.get("estimated_peak_usd",row["reserve_usd"]) for row in rows)
    if len(rows) >= args.max_calls or spent >= args.max_usd:
        (ledger/"STOP.json").write_text(json.dumps({"reason":"configured_budget_exhausted"}),encoding="utf-8")
        return 1
    try:
        observation = json.loads(sys.stdin.readline())
        client = DeepSeekClient(ledger,{},max_usd=args.max_usd-spent,max_tokens=384,thinking="disabled")
        action = client.complete(SYSTEM,observation,f"call-{len(rows):03}")
        print(json.dumps(action))
    except Exception as exc:
        (ledger/"STOP.json").write_text(json.dumps({"reason":type(exc).__name__}),encoding="utf-8")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
