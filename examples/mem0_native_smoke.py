"""Zero-API native add/search/update/fresh-process smoke, with explicit scripted facts."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trustmem_diagnostics.native_mem0 import Mem0Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedding-path", required=True, help="Existing offline BGE-small ONNX directory; no download")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    counter = [0]
    text = "The smoke project Gateboard has verification status pending."
    def scripted(messages):
        counter[0] += 1
        if counter[0] == 1:
            return json.dumps(dict(facts=[text]))
        if counter[0] == 2:
            return json.dumps(dict(memory=[dict(id="0", text=text, event="ADD")]))
        raise RuntimeError("No extra scripted inference calls are authorized")
    store = Mem0Store(output / "store", args.embedding_path, scripted)
    try:
        added = store.add(text)
        first = store.search("Gateboard verification status")
        assert first["results"][0]["memory"] == text
        oid = first["results"][0]["id"]
        update = store.update(oid, "The smoke project Gateboard has verification status complete.")
        (output/"operations.json").write_text(json.dumps(dict(add=added,search=first,update=update),indent=2),encoding="utf-8")
    finally:
        store.close()
    child = subprocess.run([sys.executable,"-B","-m","trustmem_diagnostics.native_mem0",
        "--store",str(output/"store"),"--embedding-path",args.embedding_path,"--query","Gateboard verification status"],
        capture_output=True,text=True,check=True,env={**os.environ,"PYTHONPATH":str(Path(__file__).resolve().parents[1])})
    restored = json.loads(child.stdout)
    assert restored["search"]["results"][0]["id"] == oid
    assert restored["search"]["results"][0]["memory"].endswith("status complete.")
    result = dict(status="complete",external_model_calls=0,scripted_writer_calls=counter[0],
        native_inference_pipeline=True,native_search=True,native_update=True,fresh_process_disk_read=True)
    (output/"result.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
