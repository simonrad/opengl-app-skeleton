#!/usr/bin/env python

'''
Some simple 2D graphics with glfw and PyOpenGL, and sound with pyaudio.

This example outputs a sine wave sound, whose frequency can be controlled with the up/down arrow keys.

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
    x Separate MyProgram into rendering vs. non-rendering main methods
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
import sys
import time

import my_utils


# Audio constants
SAMPLE_RATE = 44100
TARGET_TIME_SPAN = 0.015
PA_BUFFER_SIZE = 512


class MyProgram(object):

    def __init__(self, window, output_stream):
        self.window = window
        self.output_stream = output_stream
        self.sine_freq = 440
        self.phase = 0.0

        glfw.set_key_callback(window, self._key_callback)
        self._initialize_viewport()
        self._initialize_opengl()

    def _key_callback(self, window, key, scancode, action, modifier_bits):
        if key in (ord('I'), glfw.KEY_UP) and action in (glfw.PRESS, glfw.REPEAT):
            self.sine_freq *= 2 ** (1 / 12.)
        if key in (ord('K'), glfw.KEY_DOWN) and action in (glfw.PRESS, glfw.REPEAT):
            self.sine_freq /= 2 ** (1 / 12.)

    @my_utils.print_elapsed_time_between_calls(elapsed_threshold = 0.006)
    def between_frames(self):
        self._perform_audio()

    @my_utils.print_elapsed_time_between_calls()
    def render_frame(self):
        self._render()
        print

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

    def _render(self):
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
