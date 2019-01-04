#!/usr/bin/env python

'''
Some simple 2D graphics with glfw and PyOpenGL, and sound with pyaudio.

Install dependencies with:
  brew install glfw portaudio
  pip install glfw pyaudio PyOpenGL PyOpenGL_accelerate

TODO:
  - Do something with pyaudio
      - Output a simple sine wave
  - Get some keyboard input
      - Change pitch of the sine wave
  - Create a threadsafe producer/consumer stream class
      - Use a threading.Lock() to lock all operations
      - Operations
          - Produce new slice at right end
          - Read any slice
          - Delete slice at left end
          - Get index of right/left end
          - Get timestamp of last write/delete operation
          - Get time span between deleter and writer
          - PyAudio callbacks to read/write to PyAudio
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
          - If less than ~2 pages is available, wait
          - If many pages are available, constrain the search space to the most recent ~3 pages
'''

import glfw
import OpenGL.GL as gl
import pyaudio
import time


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
        print "{:.3f} seconds elapsed between frames. FPS = {:.1f}".format(elapsed, fps)
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
    # Initialize the library
    if not glfw.init():
        return

    # Create a windowed mode window and its OpenGL context
    window = glfw.create_window(640, 480, "Hello World", None, None)
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


if __name__ == "__main__":
    main()
