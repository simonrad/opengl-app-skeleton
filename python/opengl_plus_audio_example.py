#!/usr/bin/env python

'''
Some simple 2D graphics with glfw and PyOpenGL, and sound with pyaudio.
This example outputs a sine wave sound, whose frequency can be controlled with the up/down arrow keys.

Install dependencies with:
    brew install glfw portaudio
    pip install glfw pyaudio PyOpenGL PyOpenGL_accelerate
'''

import glfw
import math
import OpenGL.GL as gl
import pyaudio
import sys
import time

import my_utils


# Audio constants
SAMPLE_RATE = 44100
PA_BUFFER_SIZE = 512 # Smaller value -> lower latency

# This is the targeted amount of buffer (in seconds) between the producer (MyProgram) and the consumer (PyAudio) of the ThreadsafeStream.
# Smaller values keep the latency low (e.g. so that when you press up or down you hear the effect immediately).
# But if the value is too small then the main loop (MyProgram._perform_audio()) may not replenish the ThreadsafeStream fast enough, leading to drops in audio.
# An alternative architecture would be to have the PyAudio callback (which runs on a separate thread) generate audio on demand,
# and the main thread (which is the only thread that can process GLFW input) simply sends keyboard/mouse input signals to a threadsafe object that the PyAudio callback can read from.
# The current architecture lets you do almost everything from a single thread (the main thread).
TARGET_TIME_SPAN = 0.015


class MyProgram(object):

    def __init__(self, window, output_stream):
        self.window = window
        self.output_stream = output_stream
        self.sine_freq = 440
        self.phase = 0.0

        self.num_samples_to_render = 400
        # Start of next page should be after the start of current page + self.min_samples_to_advance
        self.min_samples_to_advance = 400
        # Start of next page should be after the most recent audio index - self.max_rendering_latency_samples - self.num_samples_to_render
        self.max_rendering_latency_samples = 400 * 10
        # If less than self.min_search_space_samples are available, wait
        self.min_search_space_samples = 400 * 5

        self.last_rendered_start_index = 0
        self.last_rendered_data = [0] * self.num_samples_to_render

        glfw.set_key_callback(window, self._key_callback)
        self._initialize_viewport()
        self._initialize_opengl()

    def _key_callback(self, window, key, scancode, action, modifier_bits):
        if key in (ord('I'), glfw.KEY_UP) and action in (glfw.PRESS, glfw.REPEAT):
            self.sine_freq *= 2 ** (1 / 12.)
            print 'The sine frequency is now {:.1f}'.format(self.sine_freq)
        if key in (ord('K'), glfw.KEY_DOWN) and action in (glfw.PRESS, glfw.REPEAT):
            self.sine_freq /= 2 ** (1 / 12.)
            print 'The sine frequency is now {:.1f}'.format(self.sine_freq)

    @my_utils.print_elapsed_time_between_calls(elapsed_threshold=0.01)
    def between_frames(self):
        self._perform_audio()

    @my_utils.print_elapsed_time_between_calls(elapsed_threshold=None)
    def render_frame(self):
        self._choose_samples_to_render()
        self._render_oscilloscope()

    def _perform_audio(self):
        self.output_stream.set_index_default('pyaudio_output', 0)
        time_span = self.output_stream.get_time_span('pyaudio_output', SAMPLE_RATE, assume_right_index_movement=False)
        ## print 'time_span is {:.4f}'.format(time_span)
        num_samples_to_generate = max(0, int((TARGET_TIME_SPAN - time_span) * SAMPLE_RATE))
        ## print 'Need to generate {} samples'.format(num_samples_to_generate)
        new_chunk = []
        for i in range(num_samples_to_generate):
            new_chunk.append(
                math.sin(self.phase) * my_utils.MAX_SAMPLE
            )
            self.phase += 2 * math.pi * self.sine_freq / SAMPLE_RATE
        self.phase %= 2 * math.pi
        self.output_stream.extend(new_chunk)

    def _initialize_viewport(self):
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

    def _initialize_opengl(self):
        # Turn on antialiasing
        gl.glEnable(gl.GL_LINE_SMOOTH)
        gl.glEnable(gl.GL_POLYGON_SMOOTH)
        gl.glHint(gl.GL_LINE_SMOOTH_HINT, gl.GL_NICEST);
        gl.glHint(gl.GL_POLYGON_SMOOTH_HINT, gl.GL_NICEST);
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA);

    def _choose_samples_to_render(self):
        '''
        Updates the following two member vars:
            self.last_rendered_start_index
            self.last_rendered_data
        '''
        assert self.max_rendering_latency_samples > self.min_search_space_samples

        max_index = self.output_stream.right_index - self.num_samples_to_render
        min_index = max(
            max_index - self.max_rendering_latency_samples,
            self.last_rendered_start_index + self.min_samples_to_advance,
        )

        if (max_index - min_index) < self.min_search_space_samples:
            return # No change to what is rendered; wait for more samples

        search_window_data = self.output_stream.get_slice(min_index)
        best_window_offset = self._find_best_match(search_window_data)
        assert self.output_stream.left_index <= min_index

        self.last_rendered_start_index = min_index + best_window_offset
        self.last_rendered_data = search_window_data[best_window_offset : best_window_offset + self.num_samples_to_render]
        assert len(self.last_rendered_data) == self.num_samples_to_render
        self._rendering_updated()

    @my_utils.print_elapsed_time_between_calls(elapsed_threshold=None)
    def _rendering_updated(self):
        ''' Just a dummy function that's called when the self.last_rendered_data is changed. '''
        pass

    def _find_best_match(self, search_window_data):
        '''
        Returns the index in search_window_data (list index, not stream index)
        that is the start of the page that best matches self.last_rendered_data.
        '''
        num_samples_to_compare = min(self.num_samples_to_render, len(self.last_rendered_data))

        # TODO
        if True: # No zeros found
            return len(search_window_data) - self.num_samples_to_render

    def _render_oscilloscope(self):

        # Clear the buffer
        gl.glClearColor(0.1, 0.1, 0.1, 0)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)

        gl.glColor3f(1, 1, 0) # Yellow

        # Draw the oscilloscope
        gl.glBegin(gl.GL_LINE_STRIP)

        for i, sample in enumerate(self.last_rendered_data):
            x = 2 * i / float(len(self.last_rendered_data) - 1) - 1
            y = sample / float(my_utils.MAX_SAMPLE)
            gl.glVertex3f(x, y, 0.0)

        gl.glEnd()


def main():
    # Initialize GLFW
    # --------------------------------------------------
    assert glfw.init()

    # Create a window and its OpenGL context
    window = glfw.create_window(640, 480, 'Hello World', None, None)
    assert window
    glfw.make_context_current(window)

    # Passing 0 will turn off VSYNC so that swap_buffers() runs as fast as possible
    # Passing 1 will turn on VSYNC to avoid tearing
    glfw.swap_interval(1)


    # Initialize PyAudio
    # --------------------------------------------------
    pa = pyaudio.PyAudio()

    # Create a ThreadsafeStream object to be the pipe between the PyAudio callback thread and our main loop/thread
    my_output_stream = my_utils.ThreadsafeStream()

    # Create an output PyAudio stream that will consume from my_output_stream
    pa_output_stream = pa.open(
        output=True,
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        frames_per_buffer=PA_BUFFER_SIZE, # 1024 is the default
        stream_callback=my_output_stream.pyaudio_output_callback,
    )

    all_pa_streams = [pa_output_stream]

    for stream in all_pa_streams:
        stream.start_stream()


    # Main loop
    # --------------------------------------------------
    my_program = MyProgram(window, my_output_stream)

    buffer_swapper = my_utils.BufferSwapper(window)

    # Loop until the user closes the window
    while not glfw.window_should_close(window) and glfw.get_key(window, ord('Q')) != glfw.PRESS:
        for stream in all_pa_streams:
            assert stream.is_active()

        my_program.render_frame()

        # Start swapping front and back buffers
        buffer_swapper.start_swapping_buffers()

        while not buffer_swapper.is_done_swapping():
            glfw.poll_events() # Poll for and process events
            my_program.between_frames()
            time.sleep(0.001)

        glfw.poll_events() # Poll for and process events
        my_program.between_frames()

        # Make output immediate even when stdout is a pipe
        sys.stdout.flush()


    # Terminate GLFW and PyAudio
    # --------------------------------------------------
    for stream in all_pa_streams:
        stream.stop_stream()
        stream.close()
    pa.terminate()

    glfw.terminate()


    print 'Goodbye!'


if __name__ == '__main__':
    main()
