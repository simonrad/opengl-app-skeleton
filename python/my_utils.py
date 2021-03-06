'''
Utility functions and classes, mostly having to do with PyAudio and GLFW.
'''

import contextlib
import functools
import glfw
import pyaudio
import struct
import sys
import threading
import time


# Audio constants
MAX_SAMPLE = 2**15 - 1
MIN_SAMPLE = -2**15
BYTES_PER_SAMPLE = 2
TYPICAL_SAMPLE_RATE = 44100


def number_to_bytes(n):
    '''
    Converts n to two bytes (as a signed short).
    n can be an int or a float.
    Throws an exception unless MIN_SAMPLE <= n <= MAX_SAMPLE.
    '''
    return struct.pack('<h', n)


def bytes_to_number(b):
    '''
    Converts two bytes (as a signed short) to an int.
    '''
    return struct.unpack('<h', b)[0]


def number_list_to_bytes(number_list):
    '''
    Converts each number to two bytes (as a signed short).
    Each number can be an int or a float.
    Throws an exception unless MIN_SAMPLE <= number <= MAX_SAMPLE.
    '''
    return ''.join(number_to_bytes(n) for n in number_list)


def bytes_to_number_list(byte_string):
    '''
    Converts each pair of two bytes (as a signed short) to an int.
    '''
    assert len(byte_string) % BYTES_PER_SAMPLE == 0
    return [
        bytes_to_number(byte_string[i : i + BYTES_PER_SAMPLE])
        for i in range(0, len(byte_string), BYTES_PER_SAMPLE)
    ]


class ThreadsafeStream(object):
    '''
    A threadsafe object representing a list supporting 2 main operations:
        - extend()
        - get_slice();  like threadsafe_stream[10:20]

    When the length of the list becomes larger than max_size, the left side of
    the list is trimmed to make the list exactly max_size in length.
    The indices are preserved, however. So for example you will no longer be
    able to read index 0 of the stream.
    '''

    def __init__(self, max_size = TYPICAL_SAMPLE_RATE * 5):
        assert int(max_size) > 0
        self._lock = threading.RLock()
        self._list = [None] * int(max_size) # Circular array
        self._right_index = 0 # External index that users of this class see; actually 1 past the end
        self._index_vars = {} # Map from index_name to (index, last_updated_timestamp)
        self._last_extend_timestamp = time.time()

    def extend(self, new_slice):
        ''' Produce a new slice at the right end. '''
        with self._lock:
            for value in new_slice:
                self._list[self._right_index % len(self._list)] = value
                self._right_index += 1
            self._last_extend_timestamp = time.time()

    def get_slice(self, begin=0, end=sys.maxint):
        assert isinstance(begin, (int, long))
        assert isinstance(end,   (int, long))
        with self._lock:
            if begin < 0:
                begin = self._right_index + begin
            if end < 0:
                end = self._right_index + end
            begin = max(begin, self.left_index)
            end   = max(end,   self.left_index)
            begin = min(begin, self._right_index)
            end   = min(end,   self._right_index)
            return [
                self._list[i % len(self._list)]
                for i in range(begin, end)
            ]

    def __len__(self):
        with self._lock:
            return min(self._right_index, len(self._list))

    @property
    def lock(self):
        return self._lock

    @property
    def left_index(self):
        with self._lock:
            return max(0, self._right_index - len(self._list))

    @property
    def right_index(self):
        with self._lock:
            return self._right_index

    def set_index(self, index_name, new_value):
        with self._lock:
            self._index_vars[index_name] = (new_value, time.time())

    def set_index_default(self, index_name, new_value_if_nonexistent):
        with self._lock:
            if index_name not in self._index_vars:
                self._index_vars[index_name] = (new_value_if_nonexistent, time.time())

    def get_index(self, index_name):
        with self._lock:
            return self._index_vars[index_name][0]

    def get_index_timestamp(self, index_name):
        with self._lock:
            return self._index_vars[index_name][1]

    def get_all_index_names(self):
        with self._lock:
            return self._index_vars.keys()

    @property
    def last_extend_timestamp(self):
        with self._lock:
            return self._last_extend_timestamp

    def get_time_span(self, index_name, sample_rate, assume_right_index_movement=True, assume_index_var_movement=True):
        '''
        Get time span (in seconds) between index and writer.
        Assumes that both indices move to the right at a rate of sample_rate list items per second.
        '''
        with self._lock:
            result = (self._right_index - self.get_index(index_name)) / float(sample_rate)
            now = time.time()
            if assume_right_index_movement:
                result += now - self._last_extend_timestamp
            if assume_index_var_movement:
                result -= now - self.get_index_timestamp(index_name)
            return result

    def pyaudio_input_callback(self,
        in_data,      # Recorded data if input=True; else None
        frame_count,  # Number of samples
        time_info,    # Dictionary
        status_flags  # PaCallbackFlags
    ):
        '''
        Reads from PyAudio and writes to this ThreadsafeStream.
        Assumes 1 channel and BYTES_PER_SAMPLE bytes per sample.
        '''
        with self._lock:
            if status_flags:
                print 'Warning: status_flags is {} in pyaudio_input_callback()'.format(status_flags)
            in_numbers = bytes_to_number_list(in_data)
            assert len(in_numbers) == frame_count
            self.extend(in_numbers)
            return (None, pyaudio.paContinue)

    def pyaudio_output_callback(self,
        in_data,      # Recorded data if input=True; else None
        frame_count,  # Number of samples
        time_info,    # Dictionary
        status_flags  # PaCallbackFlags
    ):
        '''
        Consumes from this ThreadsafeStream and writes to PyAudio.
        Assumes 1 channel and BYTES_PER_SAMPLE bytes per sample.
        '''
        with self._lock:
            if status_flags:
                print 'Warning: status_flags is {} in pyaudio_output_callback()'.format(status_flags)
            self.set_index_default('pyaudio_output', 0)
            index = self.get_index('pyaudio_output')
            if index < self.left_index:
                index = self.left_index
                print 'Warning: "pyaudio_output" index fell behind the window of remembered samples'
            out_numbers = self.get_slice(index, index + frame_count)
            self.set_index('pyaudio_output', index + len(out_numbers))
            assert self.left_index <= self.get_index('pyaudio_output') <= self._right_index
            if len(out_numbers) < frame_count:
                print 'Warning: only {} samples are available to output to PyAudio; {} were requested'.format(len(out_numbers), frame_count)
                # Fill the gap with zeros
                # (We must output at least frame_count samples. Output zeros if there aren't enough samples available in this ThreadsafeStream.)
                out_numbers += [0] * (frame_count - len(out_numbers))
            assert len(out_numbers) == frame_count
            return (number_list_to_bytes(out_numbers), pyaudio.paContinue)


class BufferSwapper(object):
    '''
    Performs glfw.swap_buffers(window) on a separate thread, and lets the main thread ask if it's finished.
    '''
    def __init__(self, window):
        # Only the main thread will set() this Event to True
        # Only self._thread will clear() this Event to False
        self._is_swapping = threading.Event()

        self._window = window

        self._thread = threading.Thread(target=self._thread_procedure, name='Thread-BufferSwapper')
        self._thread.daemon = True
        self._thread.start()

    def start_swapping_buffers(self):
        self._is_swapping.set()

    def is_done_swapping(self):
        assert self._thread.is_alive()
        return self._is_swapping.is_set() == False

    def _thread_procedure(self):
        while True:
            self._is_swapping.wait()
            glfw.swap_buffers(self._window)
            self._is_swapping.clear()


def print_elapsed_time_between_calls(elapsed_threshold=0, seconds_between_reports=2.0):
    def decorator(wrapped_func):
        call_times = [time.time()]

        @functools.wraps(wrapped_func)
        def new_func(*args, **kwargs):
            now = time.time()
            elapsed = now - call_times[-1]
            freq = 1 / elapsed
            if elapsed_threshold is not None and elapsed > elapsed_threshold:
                print '{}: {:.4f} seconds elapsed between calls. Freq = {:.1f} hz'.format(wrapped_func.__name__, elapsed, freq)
            call_times.append(now)

            if seconds_between_reports is None:
                call_times[:] = call_times[-1:]
            elif call_times[-1] - call_times[0] > seconds_between_reports:
                avg_elapsed = (call_times[-1] - call_times[0]) / (len(call_times) - 1)
                avg_freq = 1 / avg_elapsed
                elapsed_intervals = [call_times[i] - call_times[i - 1] for i in range(1, len(call_times))]
                print '{}: {:.4f} seconds between calls on average. Max = {:.4f}. Min = {:.4f}. Average freq = {:.1f} hz'.format(
                    wrapped_func.__name__, avg_elapsed, max(elapsed_intervals), min(elapsed_intervals), avg_freq
                )
                call_times[:] = call_times[-1:]

            return wrapped_func(*args, **kwargs)

        return new_func

    return decorator


@contextlib.contextmanager
def timed(name):
    start_time = time.time()
    yield
    elapsed = time.time() - start_time
    print '{} took {:.5f} seconds'.format(name, elapsed)
