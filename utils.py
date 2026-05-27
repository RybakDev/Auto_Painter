"""
Utility quick reference:

- click_at(x, y, delay=0.2, count=1)
  Moves the mouse to (x, y), waits briefly, then clicks count times.

- scroll(direction="down", length=100, x=None, y=None, step=20, step_delay=0.03)
  Scrolls the mouse wheel up or down.
  Optionally moves to (x, y) before scrolling.
  Uses small repeated scrolls so movement is slower and more subtle.

- locate_image(image_path, confidence=0.8, region=None, grayscale=False, center=True)
  Searches the screen for an image file with pyautogui.locateOnScreen.
  Returns the image center as (x, y), or None if not found.
  Use center=False to return the full locate box instead.

- scan_for_color(target_hex, step=15, tolerance=0, region=None, thread_count=1)
  Takes a screenshot and searches for the closest matching color.
  target_hex should be a string like "FF00AA".
  Returns (x, y), or None if no matching color is found.

- scan_for_color_exact(target_hex, step=15)
  Slower/simple full-screen exact color search.
  Returns (x, y), or None if the exact color is not found.

- AsyncColorScanner(target_hex, step=15, tolerance=0, scan_delay=0.02,
  thread_count=4, region=None)
  Background color scanner.
  Call start(), then get_position(), then stop() when finished.

Lower-level helpers:
- hex_to_rgb(target_hex): converts "FF00AA" into (255, 0, 170).
- is_near_color(pixel, target, tolerance=0): checks color tolerance.
- color_distance(pixel, target): returns squared RGB distance.
- scan_image_for_color(...): searches an existing screenshot object.
- find_best_color_in_slice(...): worker used by threaded color scanning.
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor
import pydirectinput
import pyautogui
import ctypes

ctypes.windll.shcore.SetProcessDpiAwareness(1)  # Enable high-DPI awareness for accurate coordinates

def click_at(x,y,delay=0.2,count = 1):
    pydirectinput.moveTo(x,y)
    time.sleep(delay)
    pydirectinput.moveTo(x+1,y+1)

    for _ in range(count):
        pydirectinput.click()
        
