import json
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transcription import parse_cpp_result, select_backend, select_device, cache_signature
from worker import validate_events


class BackendTests(unittest.TestCase):
    def test_auto_prefers_cuda_then_vulkan_then_cpu(self):
        self.assertEqual(select_backend('auto', True, [{'id': 0}]), 'cuda')
        self.assertEqual(select_backend('auto', False, [{'id': 0}]), 'vulkan')
        self.assertEqual(select_backend('auto', False, []), 'cpu')

    def test_explicit_gpu_requests_cannot_silently_use_cpu(self):
        for requested in ('cuda', 'vulkan'):
            with self.assertRaises(RuntimeError):
                select_backend(requested, False, [])

    def test_device_selection_prefers_amd_but_honors_user(self):
        devices = [{'id': 0, 'amd': False}, {'id': 1, 'amd': True}]
        self.assertEqual(select_device('auto', devices)['id'], 1)
        self.assertEqual(select_device(0, devices)['id'], 0)
        with self.assertRaises(ValueError):
            select_device(4, devices)

    def test_cpp_milliseconds_are_converted_to_seconds(self):
        result = parse_cpp_result({'result': {'language': 'en'}, 'transcription': [
            {'offsets': {'from': 1230, 'to': 2460}, 'text': ' example '}]})
        self.assertEqual(result['segments'], [{'start': 1.23, 'end': 2.46, 'text': 'example'}])

    def test_invalid_cpp_boundaries_rejected(self):
        for start, end in [(2, 1), (-1, 4), (0, float('nan'))]:
            with self.assertRaises(ValueError):
                parse_cpp_result({'transcription': [{'offsets': {'from': start, 'to': end}, 'text': 'bad'}]})

    def test_cache_invalidates_for_model_language_and_backend(self):
        path = Path(__file__)
        initial = cache_signature(path, {'model': 'large-v3'}, 'cuda')
        self.assertNotEqual(initial, cache_signature(path, {'model': 'base.en'}, 'cuda'))
        self.assertNotEqual(initial, cache_signature(path, {'model': 'large-v3', 'language': 'fr'}, 'cuda'))
        self.assertNotEqual(initial, cache_signature(path, {'model': 'large-v3'}, 'vulkan'))

    def test_render_rejects_out_of_bounds_and_nonfinite_regions(self):
        for start, end in [(1, 1), (-1, 2), (1, 20), (1, float('inf'))]:
            with self.assertRaises(ValueError):
                validate_events([{'start': start, 'end': end}], 10)

    def test_overlapping_regions_are_merged_before_render(self):
        events = validate_events([{'start': 1, 'end': 2}, {'start': 1.5, 'end': 3}], 10)
        self.assertEqual([(e.start, e.end) for e in events], [(1, 3)])


if __name__ == '__main__':
    unittest.main()
