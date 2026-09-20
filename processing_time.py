"""Stage-aware remaining-time estimates; initial budgets are deliberately approximate."""
import math
import time


def initial_budget(action, duration, config, backend):
    duration = max(0., float(duration))
    if action == 'analyze':
        model = str(config.get('vulkan_model' if backend == 'vulkan' else 'model', 'base.en'))
        size = next((name for name in ('large', 'medium', 'small', 'base', 'tiny') if model.startswith(name)), 'large')
        # Cold-start assumptions, refined with measured stage progress on this run.
        factors = {'cpu': (.25, .45, 1.2, 2.5, 4.0),
                   'cuda': (.025, .04, .07, .13, .23),
                   'vulkan': (.05, .08, .18, .35, .65)}
        index = ('tiny', 'base', 'small', 'medium', 'large').index(size)
        factor = factors.get(backend, factors['cpu'])[index]
        return {'prepare': 5 + duration * .015, 'load': 20 + index * 5,
                'transcribe': max(3, duration * factor), 'align_load': 10,
                'align': max(3, duration * (.04 if backend == 'cuda' else .18)), 'finish': 2}
    if action in ('render', 'preview'):
        encoder = config.get('export_encoder', 'copy' if config.get('export_quality', 'original') == 'original' else 'auto')
        factor = .04 if action == 'preview' or encoder == 'copy' else .8 if encoder.startswith('lib') else .2
        return {'prepare': 5., 'render': max(3, duration * factor), 'finish': 2.}
    return {}


class RemainingTime:
    def __init__(self, action, duration, config, backend, clock=time.monotonic):
        self.clock = clock
        self.budgets = initial_budget(action, duration, config, backend)
        self.phase = next(iter(self.budgets), None)
        self.started = clock()
        self.fraction = 0.
        self.measured_total = None

    def observe(self, phase, percent=0):
        if phase not in self.budgets:
            return
        phases = list(self.budgets)
        if self.phase and phases.index(phase) < phases.index(self.phase):
            return  # Late/duplicate messages must not restore already finished work.
        if phase != self.phase:
            self.phase, self.started = phase, self.clock()
            self.fraction, self.measured_total = 0., None
        fraction = min(1., max(0., float(percent) / 100))
        elapsed = self.clock() - self.started
        if math.isfinite(fraction) and fraction > self.fraction:
            self.fraction = fraction
            if elapsed >= .25 and fraction >= .01:
                measured = elapsed / fraction
                self.measured_total = measured if self.measured_total is None else .35 * self.measured_total + .65 * measured

    def remaining(self):
        if not self.phase:
            return None
        phases = list(self.budgets)
        future = sum(self.budgets[p] for p in phases[phases.index(self.phase) + 1:])
        elapsed = max(0, self.clock() - self.started)
        if self.fraction >= 1:
            current = 1.
        else:
            predicted = self.measured_total if self.measured_total is not None else self.budgets[self.phase]
            # A slow batch/load can overrun an estimate. Revise it, never show zero
            # while processing is active or keep counting down into negative time.
            current = max(1., predicted - elapsed, elapsed * .25 if elapsed > predicted else 0.)
        return current + future


def format_duration(seconds):
    seconds = max(0, math.ceil(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f'{hours}h {minutes:02d}m {seconds:02d}s'
    return f'{minutes}m {seconds:02d}s' if minutes else f'{seconds}s'
