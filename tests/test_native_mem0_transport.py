"""Optional framework transport can be imported and failure-tracked without SDKs."""
import unittest
from trustmem_diagnostics.native_mem0 import ClientConfig, NativeTransport


class NativeTransportTests(unittest.TestCase):
    def test_original_native_messages_are_not_rewritten(self):
        seen=[]
        messages=[dict(role="user",content="native update prompt")]
        transport=NativeTransport(ClientConfig(client=lambda m: seen.append(m) or '{"memory":[]}'))
        self.assertEqual(transport.generate_response(messages),'{"memory":[]}')
        self.assertIs(seen[0],messages)
        self.assertEqual(transport.failures,[])

    def test_transport_failure_stays_visible_when_native_code_catches_it(self):
        transport=NativeTransport(ClientConfig())
        with self.assertRaises(RuntimeError):
            transport.generate_response([])
        self.assertEqual(transport.failures,["RuntimeError"])


if __name__ == "__main__":
    unittest.main()
