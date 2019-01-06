#!/usr/bin/env python

'''
Some simple 2D graphics with glfw and PyOpenGL, and sound with pyaudio.

Install dependencies with:
  brew install glfw portaudio
  pip install glfw pyaudio PyOpenGL PyOpenGL_accelerate

TODO:
  - Do something with pyaudio
      x Output a simple sine wave using blocking mode
      - Output a simple sine wave using a callback
  - Get some keyboard input
      - Change pitch of the sine wave
  - Create a threadsafe producer/consumer stream class
      - Use a threading.Lock() to lock all operations
      - Operations
          - Produce new slice at right end
          - Read any slice
          - Keep up to N samples (circular array)
          - Get index of right/left end
          - Get/set index variables
          - PyAudio callbacks to read/write to PyAudio
          - Get timestamp of last write/set_index operation
          - Get time span between index and writer
          - Get/set a "complete" flag
  - Create a musical keyboard?
      - ADSR style
          - 3 states: ADS phase, Release phase, FastRelease phase
              - FastRelease happens if you press a key during Release phase
          - Have many harmonics. Upper harmonics start out louder (and random loudness), then decay to normal
  - Write an oscilloscope app
      - Start of a page should be at a "zero" (upward-sloped crossing of the x-axis)
          - If no zeros are available, give up and render the most recent page
      - Search for the zero that best matches the previously-rendered page
          - Either sum-of-differences or correlation
      - Search constraints
          - Start of next page should be after the end of current page
          - If less than ~N pages are available, wait
          - If many pages are available, constrain the search space to the most recent ~M pages
'''

import glfw
import math
import OpenGL.GL as gl
import pyaudio
import struct
import time


# TODO: BUFFER_SIZE is unused
# TODO: Ensure the main thread can still execute while the callback is executing (otherwise deadlock)


# Audio constants
SAMPLE_RATE = 44100
BUFFER_SIZE = 16384 # This is the max that PyAudio will allow
MAX_SAMPLE = 2**15 - 1
MIN_SAMPLE = -2**15
BYTES_PER_SAMPLE = 2


def number_to_bytes(n):
    '''
    Converts n to two bytes (as a signed short)
    n can be an int or a float
    Throws an exception unless MIN_SAMPLE <= n <= MAX_SAMPLE
    '''
    return struct.pack('<h', n)


def bytes_to_number(b):
    '''
    Converts two bytes (as a signed short) to an int
    '''
    return struct.unpack('<h', b)[0]


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


class MyProgram(object):

    def __init__(self, window):
        self.window = window
        self.time_of_last_frame = time.time()

    def perform_frame(self):
        self.before_frame()
        self.reinitialize_viewport()
        self.initialize_opengl()
        self.render()

    def before_frame(self):
        now = time.time()
        elapsed = now - self.time_of_last_frame
        fps = 1 / elapsed
        print '{:.3f} seconds elapsed between frames. FPS = {:.1f}'.format(elapsed, fps)
        self.time_of_last_frame = now

    def reinitialize_viewport(self):
        (w, h) = glfw.get_window_size(self.window)

        # Paint within the whole window
        gl.glViewport(0, 0, w, h)

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
    play_audio_with_callback()
    return

    # Initialize the library
    if not glfw.init():
        return

    # Create a windowed mode window and its OpenGL context
    window = glfw.create_window(640, 480, 'Hello World', None, None)
    if not window:
        glfw.terminate()
        return

    # Make the window's context current
    glfw.make_context_current(window)

    my_program = MyProgram(window)

    # Loop until the user closes the window
    while not glfw.window_should_close(window):
        my_program.perform_frame()

        # Swap front and back buffers
        glfw.swap_buffers(window)

        # Poll for and process events
        glfw.poll_events()

    glfw.terminate()

    print 'Goodbye!'


if __name__ == '__main__':
    main()
