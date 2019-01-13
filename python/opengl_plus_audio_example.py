#!/usr/bin/env python

'''
Some simple 2D graphics with glfw and PyOpenGL, and sound with pyaudio.

Install dependencies with:
    brew install glfw portaudio
    pip install glfw pyaudio PyOpenGL PyOpenGL_accelerate

TODO:
    x Do something with pyaudio
        x Output a simple sine wave using blocking mode
        x Output a simple sine wave using a callback
    x Potential Problem: Resizing the window blocks the main loop
        x Should be OK. Just output zeros to PyAudio when the main loop isn't keeping up
    x Get some keyboard input
        x Quit the program when 'Q' is pressed
    x Fix the coordinates on Retina screens
    x Create a threadsafe producer/consumer stream class
        x Use a threading.Lock() to lock all operations
        x Operations
            x Produce new slice at right end
            x Read any slice
            x Keep up to N samples
            x Get index of right/left end
            x Get/set index variables
            x Get timestamp of last write/set_index operation
            x Get time span between index and writer
            x PyAudio callbacks to read/write to PyAudio
    x Refactor the sine wave to integrate with the GLFW flow
    x Get some keyboard/mouse input
        x Change pitch of the sine wave
    x Performance
        x Try glfw.swap_interval(0)
            - That worked! For the most part. FPS is now usually 600 but occasionally drops to 30.
                - Not sure why the FPS occasionally drops, but seems related to swap_buffers()
                    - Usually one of the OpenGL calls is slow, but sometimes it happens when all of them are fast
                    - Turning off PyAudio had no effect
                    - If I don't do swap_buffers(), the FPS never drops
            - glfw.swap_interval(0) may lead to tearing
            - So, best not to rely on swap_buffers() being fast
        x Measure glFlush() time
        x Try changing the OpenGL version
        - Are performance improvements necessary?
        x Remove the swap_buffers() call and see how responsive the audio can be
            - Even without swap_buffers(), the main thread sometimes gets blocked for up to 0.07 seconds
        x Call swap_buffers() from another thread
            - If I can't get swap_buffers() to be faster, at least this would let me process events with low latency
            - Will require some work: A separate thread, condition variables, and separating MyProgram into rendering vs. non-rendering main methods
            - Results: The main loop is now almost never blocked for more than 0.006 seconds
        - Other ideas
            - Check the FPS of the SIGIL app?
            - Try fullscreen mode?
    - Separate MyProgram into rendering vs. non-rendering main methods
    - Clean up the code
    - Write an oscilloscope app
        - Start of a page should be at a "zero" (upward-sloped crossing of the x-axis)
            - If no zeros are available, give up and render the most recent page
        - Search for the zero that best matches the previously-rendered page
            - Either sum-of-differences or correlation
        - Search constraints
            - Start of next page should be after the end of current page
            - If less than ~N pages are available, wait
            - If many pages are available, constrain the search space to the most recent ~M pages
    - Create a musical keyboard?
        - ADSR style
            - 3 states: ADS phase, Release phase, FastRelease phase
                - FastRelease happens if you press a key during Release phase
            - Have many harmonics. Upper harmonics start out louder (and random loudness), then decay to normal
                - Idea: Have the harmonics change their loudness randomly over time
        - Abstract the keyboard from the (single note) synth
            - Keyboard will re-construct the synth if it shuts off and key is pressed
            - Don't bother adding more abstraction than that
        - Controller ideas
            - Control different synths with different parts of the keyboard
            - Let you "slide" smoothly between notes (instead of letting you play multiple notes at once) by pressing one key while holding another
            - Control a synth with the mouse (volume and pitch)
'''

import glfw
import math
import OpenGL.GL as gl
import pyaudio
import struct
import sys
import threading
import time


# Audio constants
SAMPLE_RATE = 44100
MAX_SAMPLE = 2**15 - 1
MIN_SAMPLE = -2**15
BYTES_PER_SAMPLE = 2
TARGET_TIME_SPAN = 0.05


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


def play_audio_with_callback():
    data = ''.join(
        number_to_bytes(
            math.sin(
                (float(t) / SAMPLE_RATE) * 2 * math.pi * 440
            ) * MAX_SAMPLE
        )
        for t in range(int(SAMPLE_RATE * 2))
    )

    class Closure:
        data_index = 0

    pa = pyaudio.PyAudio()

    def callback(in_data, frame_count, time_info, status):
        # Note: A sleep in the callback less than time.sleep(0.02) does not affect the continuity of the sound
        # Note: The main thread can still execute while the callback is executing
        data_chunk = data[Closure.data_index : Closure.data_index + frame_count * BYTES_PER_SAMPLE]
        Closure.data_index += frame_count * BYTES_PER_SAMPLE
        return (data_chunk, pyaudio.paContinue)

    output_stream = pa.open(
        output=True,
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        frames_per_buffer=1024, # This is the default
        stream_callback=callback,
    )

    start_time = time.time()
    output_stream.start_stream()

    # Wait for stream to finish
    while output_stream.is_active():
        time.sleep(0.01)

    print 'done playing audio. elapsed = {:.2f}'.format(time.time() - start_time)

    output_stream.stop_stream()
    output_stream.close()
    pa.terminate()


def play_audio_blocking():
    pa = pyaudio.PyAudio()

    output_stream = pa.open(
        output=True,
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        frames_per_buffer=16384, # This is the max buffer size that PyAudio will allow
    )

    data = ''.join(
        number_to_bytes(
            math.sin(
                (float(t) / SAMPLE_RATE) * 2 * math.pi * 440
            ) * MAX_SAMPLE
        )
        for t in range(int(16384 - 2))
    )

    time.sleep(0.2)
    print 'write_available =', output_stream.get_write_available()
    start_time = time.time()
    output_stream.write(data)
    elapsed_done_writing = time.time() - start_time
    # print 'done writing audio. elapsed = {:.2f}'.format(time.time() - start_time)

    time.sleep(0.2)
    print 'write_available =', output_stream.get_write_available()

    output_stream.stop_stream()
    output_stream.close()
    pa.terminate()

    elapsed_done_playing = time.time() - start_time
    # print 'done playing audio. elapsed = {:.2f}'.format(time.time() - start_time)

    print 'elapsed_done_writing = {:.2f}'.format(elapsed_done_writing)
    print 'elapsed_done_playing = {:.2f}'.format(elapsed_done_playing)


class ThreadsafeStream(object):
    '''
    A threadsafe object representing a list supporting 2 main operations:
        - extend()
        - __getslice__();  i.e. threadsafe_stream[10:20]

    When the length of the internal list becomes larger than maxSize, the left
    side of the list is trimmed to make the list exactly maxSize in length.
    The indices are preserved, however. So for example you will no longer be
    able to read index 0 of the stream.
    '''

    def __init__(self, maxSize=SAMPLE_RATE * 5):
        self._lock = threading.RLock()
        self._maxSize = maxSize
        self._list = []
        self._start_index = 0
        self._index_vars = {} # Map from index_name to (index, last_updated_timestamp)
        self._last_extend_timestamp = time.time()

    def extend(self, new_slice):
        ''' Produce a new slice at the right end. '''
        with self._lock:
            self._list.extend(new_slice)
            self._last_extend_timestamp = time.time()
            num_to_delete = len(self._list) - self._maxSize
            if num_to_delete > 0:
                del self._list[0 : num_to_delete]
                self._start_index += num_to_delete

    def __getslice__(self, begin, end):
        with self._lock:
            if 0 <= begin < sys.maxint:
                begin = max(0, begin - self._start_index)
            if 0 <= end < sys.maxint:
                end = max(0, end - self._start_index)
            return self._list[begin : end]

    def __len__(self, yyy):
        with self._lock:
            return len(self._list)

    @property
    def lock(self):
        return self._lock

    @property
    def left_index(self):
        with self._lock:
            return self._start_index

    @property
    def right_index(self):
        with self._lock:
            return self._start_index + len(self._list)

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
            result = (self.right_index - self.get_index(index_name)) / float(sample_rate)
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
            out_numbers = self[index : index + frame_count]
            self.set_index('pyaudio_output', index + len(out_numbers))
            assert self.left_index <= self.get_index('pyaudio_output') <= self.right_index
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


class MyProgram(object):

    def __init__(self, window, output_stream):
        self.window = window
        self.output_stream = output_stream
        self.time_of_last_frame = time.time()
        self.sine_freq = 440
        self.phase = 0.0
        glfw.set_key_callback(window, self.key_callback)

    def key_callback(self, window, key, scancode, action, modifier_bits):
        if key in (ord('I'), glfw.KEY_UP) and action in (glfw.PRESS, glfw.REPEAT):
            self.sine_freq *= 2 ** (1 / 12.)
        if key in (ord('K'), glfw.KEY_DOWN) and action in (glfw.PRESS, glfw.REPEAT):
            self.sine_freq /= 2 ** (1 / 12.)

    def perform_frame(self):
        self.before_frame()
        self.perform_audio()
        self.initialize_viewport() # Note: This could be called just once at startup, instead
        self.initialize_opengl()   # Note: This could be called just once at startup, instead
        self.render()

    def before_frame(self):
        now = time.time()
        elapsed = now - self.time_of_last_frame
        fps = 1 / elapsed
        print
        print '{:.3f} seconds elapsed between frames. FPS = {:.1f}'.format(elapsed, fps)
        self.time_of_last_frame = now

    def perform_audio(self):
        self.output_stream.set_index_default('pyaudio_output', 0)
        time_span = self.output_stream.get_time_span('pyaudio_output', SAMPLE_RATE, assume_right_index_movement=False)
        print 'time_span is {:.4f}'.format(time_span)
        num_samples_to_generate = max(0, int((TARGET_TIME_SPAN - time_span) * SAMPLE_RATE))
        print 'Need to generate {} samples'.format(num_samples_to_generate)
        new_chunk = []
        for i in range(num_samples_to_generate):
            new_chunk.append(
                math.sin(self.phase) * MAX_SAMPLE
            )
            self.phase += 2 * math.pi * self.sine_freq / SAMPLE_RATE
        self.phase %= 2 * math.pi
        self.output_stream.extend(new_chunk)

    def initialize_viewport(self):
        return # This function currently has no effect, since all these settings are the default settings

        # Note: On Retina screens, pixel_w is 2x greater than window_w
        (window_w, window_h) = glfw.get_window_size(self.window)
        (pixel_w, pixel_h) = glfw.get_framebuffer_size(self.window)

        # Paint within the whole window
        gl.glViewport(0, 0, pixel_w, pixel_h)

        # Set orthographic projection (2D only)
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glLoadIdentity()

        # The bottom-left window corner's OpenGL coordinates are (-1, -1)
        # The top-right window corner's OpenGL coordinates are (+1, +1)
        gl.glOrtho(-1, 1, -1, 1, -1, 1)

    def initialize_opengl(self):
        # Turn on antialiasing
        gl.glEnable(gl.GL_LINE_SMOOTH)
        gl.glEnable(gl.GL_POLYGON_SMOOTH)
        gl.glHint(gl.GL_LINE_SMOOTH_HINT, gl.GL_NICEST);
        gl.glHint(gl.GL_POLYGON_SMOOTH_HINT, gl.GL_NICEST);
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA);

    def render(self):
        # Clear the buffer
        gl.glClearColor(0.1, 0.1, 0.1, 0)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)

        # Draw some points
        gl.glBegin(gl.GL_LINE_STRIP)

        gl.glColor3f(1, 0, 0)
        gl.glVertex3fv((-.95, -.95, 0))

        gl.glColor3f(0, 1, 0)
        gl.glVertex3fv((-.95, +.95, 0))

        gl.glColor3f(0, 0, 1)
        gl.glVertex3fv((+.95, -.95, 0))

        gl.glColor3f(1, 1, 0) # Yellow
        gl.glVertex3fv((+.95, +.95, 0))

        gl.glEnd()


def main():
    # Initialize GLFW
    assert glfw.init()

    # Create a windowed mode window and its OpenGL context
    window = glfw.create_window(640, 480, 'Hello World', None, None)
    assert window
    glfw.make_context_current(window)

    # Passing 0 will turn off VSYNC so that swap_buffers() runs as fast as possible
    # Passing 1 will turn on VSYNC to avoid tearing
    glfw.swap_interval(1)

    # Initialize PyAudio
    pa = pyaudio.PyAudio()

    # Create a ThreadsafeStream object to be the pipe between the PyAudio callback thread and our main loop/thread
    my_output_stream = ThreadsafeStream()

    # Create an output PyAudio stream that will consume from my_output_stream
    pa_output_stream = pa.open(
        output=True,
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        frames_per_buffer=1024, # This is the default
        stream_callback=my_output_stream.pyaudio_output_callback,
    )
    pa_output_stream.start_stream()

    my_program = MyProgram(window, my_output_stream)

    buffer_swapper = BufferSwapper(window)

    # Loop until the user closes the window
    while not glfw.window_should_close(window) and glfw.get_key(window, ord('Q')) != glfw.PRESS:
        assert pa_output_stream.is_active()

        my_program.perform_frame()

        # Start swapping front and back buffers
        buffer_swapper.start_swapping_buffers()

        while not buffer_swapper.is_done_swapping():
            glfw.poll_events()
            time.sleep(0.001)

        # Poll for and process events
        glfw.poll_events()

        # Make output immediate even when stdout is a pipe
        sys.stdout.flush()

    pa_output_stream.stop_stream()
    pa_output_stream.close()
    pa.terminate()

    glfw.terminate()

    print 'Goodbye!'


if __name__ == '__main__':
    main()
