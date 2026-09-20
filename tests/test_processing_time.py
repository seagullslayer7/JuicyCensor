import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from processing_time import RemainingTime, format_duration

class RemainingTimeTests(unittest.TestCase):
    def tracker(self, action='analyze', backend='cpu', **config):
        self.now = 0.
        return RemainingTime(action, 600, config, backend, lambda: self.now)

    def test_first_analysis_and_export_have_estimates_without_history(self):
        for action in ('analyze', 'render', 'preview'):
            for backend in ('cpu', 'cuda', 'vulkan'):
                with self.subTest(action=action, backend=backend):
                    self.assertGreater(self.tracker(action, backend).remaining(), 0)

    def test_model_and_backend_affect_initial_estimate(self):
        base = self.tracker(model='base.en').remaining()
        self.assertGreater(self.tracker(model='large-v3').remaining(), base)
        self.assertLess(self.tracker(backend='cuda', model='base.en').remaining(), base)

    def test_live_render_speed_replaces_initial_guess(self):
        t = self.tracker('render'); t.observe('render', 0)
        self.now = 10; t.observe('render', 25)
        self.assertAlmostEqual(t.remaining(), 32)  # 30 seconds rendering plus finalization.
        self.now = 12; t.observe('render', 50)
        self.assertLess(t.remaining(), 20)

    def test_analysis_phase_reset_excludes_completed_work(self):
        t = self.tracker();t.observe('transcribe', 0)
        self.now=20;t.observe('transcribe', 50)
        before=t.remaining()
        t.observe('align', 0)
        self.assertLess(t.remaining(), before)
        self.now=25;t.observe('align', 50)
        self.assertAlmostEqual(t.remaining(), 7)

    def test_stalled_phase_never_counts_down_to_zero_or_negative(self):
        t=self.tracker('render');t.observe('render', 0)
        self.now=10000
        self.assertTrue(math.isfinite(t.remaining()))
        self.assertGreater(t.remaining(), 0)

    def test_out_of_order_updates_do_not_restore_previous_stage(self):
        t=self.tracker();t.observe('align', 50)
        t.observe('transcribe', 80)
        self.assertEqual(t.phase, 'align')
        t.observe('align', 25)
        self.assertEqual(t.fraction, .5)

    def test_readable_elapsed_and_remaining_durations(self):
        self.assertEqual(format_duration(0), '0s')
        self.assertEqual(format_duration(80), '1m 20s')
        self.assertEqual(format_duration(3750), '1h 02m 30s')

if __name__ == '__main__': unittest.main()
