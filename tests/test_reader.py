import json
from pathlib import Path
import tempfile
import unittest
from trustmem_runtime.data import canonical
from trustmem_runtime.fixtures import build
from trustmem_runtime.run import read_case
from trustmem_runtime.reader import CaseTools, run_session


class ReaderTests(unittest.TestCase):
    def test_same_tools_preserve_unfinished_and_wrong_submission(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            build(root/"cases")
            case=read_case(root/"cases/quality.case.json")
            source=case["initial_source"];task=case["tasks"][0]["request"]
            seen=[]
            def query_only(system,payload):
                seen.append(payload)
                return dict(action="query",scope="full")
            result=run_session(task=task,source_id=source,notes=[],respond=query_only,
                tools=CaseTools(case["sources"]),output=root/"last",max_actions=1)
            self.assertEqual(result["status"],"unfinished")
            self.assertEqual(result["generated_not_delivered"],1)
            self.assertFalse((root/"last/delivery.json").exists())
            self.assertEqual(seen[0]["remaining_actions"],1)
            result=run_session(task=task,source_id=source,notes=[],respond=lambda *_:dict(action="submit",value=0),
                tools=CaseTools(case["sources"]),output=root/"wrong")
            self.assertEqual(result["value"],0)
            self.assertEqual(result["status"],"submitted")

    def test_notes_and_task_bound_calculation_need_no_source_read(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            margin=dict(kind="margins",source_id="A",left={"correct":95,"incorrect":5},right={"90":80,"50":20},total=100)
            notes=[dict(id="native-id",memory="Keep this exact observation: "+canonical(margin))]
            def policy(system,payload):
                if not payload["tool_trace"]:
                    return dict(action="calculate",evidence=["native-id"])
                return dict(action="submit",value=payload["tool_trace"][-1]["result"]["value"])
            task=dict(kind="quality",a="correct",cutoff=80,numerator=9,denominator=10)
            result=run_session(task=task,source_id="A",notes=notes,respond=policy,
                tools=CaseTools({}),output=root/"stream",max_actions=2)
            self.assertEqual(result["value"],1)
            self.assertEqual(result["source_read_bytes"],0)
            self.assertEqual(result["generated_not_delivered"],0)
            self.assertEqual(json.loads((root/"stream/t0-input.json").read_bytes())["retrieved_notes"],notes)

    def test_budget_errors_and_arithmetic_do_not_change_contract(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            task=dict(kind="quality",a="correct",cutoff=80,numerator=99,denominator=100)
            actions=iter([dict(action="calculate",evidence=["unknown"]),dict(action="quality_check",selected_correct=80,selected_total=100,threshold_numerator=99,threshold_denominator=100)])
            result=run_session(task=task,source_id="A",notes=[],respond=lambda *_:next(actions),
                tools=CaseTools({}),output=root/"stream",max_actions=2,mode="tool_first")
            self.assertEqual(result["tool_errors"],1)
            self.assertEqual(result["status"],"unfinished")
            self.assertEqual(result["trace"][-1]["result"]["input_binding"],"unverified_model_supplied_numbers")

    def test_client_cannot_mutate_logged_memory(self):
        with tempfile.TemporaryDirectory() as d:
            def policy(system,payload):
                payload["retrieved_notes"].clear()
                return dict(action="abstain")
            notes=[dict(id="n",memory="literal source")]
            run_session(task=dict(kind="marginal",a="red"),source_id="A",notes=notes,
                respond=policy,tools=CaseTools({}),output=Path(d)/"stream")
            self.assertEqual(len(notes),1)

    def test_free_and_tool_first_have_same_payload_and_actions(self):
        with tempfile.TemporaryDirectory() as d:
            seen=[]
            def policy(system,payload):
                seen.append((system,payload))
                return dict(action="submit",value=7)
            for mode in ("free","tool_first"):
                run_session(task=dict(kind="marginal",a="red"),source_id="A",notes=[],
                    respond=policy,tools=CaseTools({}),output=Path(d)/mode,mode=mode)
            self.assertEqual(seen[0][1],seen[1][1])
            self.assertNotEqual(seen[0][0],seen[1][0])

    def test_action_schema_is_explicit_but_host_does_not_repair_type_alias(self):
        with tempfile.TemporaryDirectory() as d:
            captured=[]
            def policy(system,payload):
                captured.append((system,payload))
                return dict(type="query",scope="full")
            event=run_session(task=dict(kind="marginal",a="red"),source_id="A",notes=[],
                respond=policy,tools=CaseTools({}),output=Path(d)/"stream")
            self.assertEqual(captured[0][1]["action_schema"]["required"],["action"])
            self.assertIn('"action":"query"',captured[0][0])
            self.assertEqual(event["status"],"interface_failure")
            self.assertEqual(event["query_calls"],0)


if __name__=="__main__":
    unittest.main()
