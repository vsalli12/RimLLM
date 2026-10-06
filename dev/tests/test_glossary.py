import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import RAG_main


class GlossaryTests(unittest.TestCase):
    def test_longest_match_keeps_source_intact_and_does_not_expand_definitions(self):
        glossary = {
            'Mechanoid': {'definition': 'A robot.'},
            'Mechanoid Signal': {'definition': 'A quest involving a mechanoid.'},
            'meal': {'definition': 'Food.'},
        }
        source = 'A MECHANOID SIGNAL was received. Mechanoid Signal remains a quest.'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'glossary.json'
            path.write_text(json.dumps(glossary), encoding='utf-8')
            result = RAG_main.add_context(source, path)
            self.assertEqual(result.split(RAG_main.REFERENCE_MARKER)[0], source)
            self.assertEqual(result.count('- Mechanoid Signal:'), 1)
            self.assertNotIn('- Mechanoid:', result)
            self.assertNotIn('- meal:', result)
            self.assertEqual(RAG_main.add_context(result, path), result)
            self.assertIn('- Mechanoid:', RAG_main.add_context(source + ' A mechanoid attacked.', path))
            self.assertEqual(RAG_main.add_context('mealtimes', path), 'mealtimes')

    def test_discovery_keeps_distinct_overlapping_terms_and_existing_definitions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'glossary.json'
            original = {'term': 'Mechanoid', 'definition': 'A robot.'}
            path.write_text(json.dumps({'Mechanoid': original}), encoding='utf-8')
            with patch.object(RAG_main, 'GLOSSARY_PATH', path), patch.object(
                    RAG_main, 'LLM_Pass', return_value={'terms': ['mechanoid', 'Mechanoid Signal']}), contextlib.redirect_stdout(io.StringIO()):
                RAG_main.additional_context_pass('A Mechanoid Signal')
            saved = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(len(saved), 2)
            self.assertEqual(saved['Mechanoid'], original)
            self.assertIn('Mechanoid Signal', saved)


if __name__ == '__main__':
    unittest.main()
