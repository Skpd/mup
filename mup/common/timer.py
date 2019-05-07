from collections import deque
from time import time, process_time


class Timer:
    timers = None
    time_fn = None

    def __init__(self, use_process_time=False):
        self.timers = deque()
        if use_process_time:
            self.time_fn = process_time
        else:
            self.time_fn = time

    def start(self):
        self.timers.append(self.time_fn())

    def end(self):
        start = self.timers.pop()
        end = self.time_fn()
        diff = end - start

        if diff < .001:
            suffix = 'μs'
            diff *= 1e6
        elif 0.001 < diff < 1:
            suffix = 'ms'
            diff *= 1e3
        else:
            suffix = 'sec'

        return '{} {}'.format(int(diff), suffix)
