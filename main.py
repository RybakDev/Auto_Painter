import ctypes
from ctypes import wintypes
from collections import defaultdict
from pathlib import Path
import time

from PIL import Image
import pydirectinput

from utils import click_at


# Drop your source image in this folder. The script uses the first supported
# image it finds alphabetically.
IMAGE_FOLDER = Path("images")
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

# Normal screen pixels. Use the visible drawable canvas edge, or set
# CANVAS_BORDER_INSET_NORMAL_PIXELS below if these include the border.
CANVAS_TOP_LEFT = (606, 92)
CANVAS_BOTTOM_RIGHT = (1312, 799)

# In-game drawable pixel resolution: (width, height).
CANVAS_RESOLUTION = (200,200)

# Optional safety inset in normal screen pixels. Useful if your chosen canvas
# points sit on the frame/border instead of the first drawable pixel edge.
CANVAS_BORDER_INSET_NORMAL_PIXELS = 0

# Keep this at 1 to paint every game pixel. Increase to 2, 3, etc. for faster
# rough previews.
DRAW_STEP = 1

# Paint only one horizontal lane of the image. Lanes are numbered from top to
# bottom, starting at 1. For example, 4 lanes means:
# lane 1 = top quarter, lane 4 = bottom quarter.
PAINT_ONLY_SELECTED_LANE = True
HORIZONTAL_LANE_COUNT = 5
HORIZONTAL_LANE_NUMBER = 1

# Set this to None for exact image colors. Lower numbers reduce brush color
# changes a lot, but the drawing becomes less detailed.
MAX_COLORS = 50

# White pixels are skipped because the canvas starts white. Lower this if very
# light colors should also be skipped; set SKIP_WHITE_PIXELS to False to paint
# every color.
SKIP_WHITE_PIXELS = True
WHITE_SKIP_MIN_CHANNEL_VALUE = 225

# Passed to click_at for every painted pixel.
CLICK_DELAY_SECONDS = 0.0001

# Used between UI actions while changing brush colors.
COLOR_CHANGE_CLICK_DELAY_SECONDS = 0.15
COLOR_CHANGE_ACTION_DELAY_SECONDS = 0.15
COLOR_CHANGE_TYPE_INTERVAL_SECONDS = 0.06
HEX_INPUT_READY_DELAY_SECONDS = 0.35
HEX_INPUT_AFTER_PASTE_DELAY_SECONDS = 0.25
USE_CLIPBOARD_FOR_HEX_INPUT = True

# Press this after switching to the game window.
START_HOTKEY = ("ctrl", "alt", "p")

# Press this while painting to pause, then press it again to resume.
PAUSE_HOTKEY = ("ctrl", "alt", "o")

VIRTUAL_KEY_CODES = {
    "ctrl": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "space": 0x20,
    "enter": 0x0D,
    "o": 0x4F,
    "p": 0x50,
}

CHANGE_COLOR_BUTTON_LOCATION = (757, 855)
EDIT_HEX_LOCATION = (1103, 705)
CONFIRM_COLOR_CHANGE_LOCATION = (877, 708)

is_paused = False
was_pause_hotkey_down = False


def normalize_hex_code(hex_code):
    hex_code = hex_code.strip().upper()
    if hex_code.startswith("#"):
        hex_code = hex_code[1:]

    if len(hex_code) != 6 or any(character not in "0123456789ABCDEF" for character in hex_code):
        raise ValueError(f"Invalid hex color: {hex_code}")

    return f"#{hex_code}"


def type_hex_code(hex_code):
    time.sleep(HEX_INPUT_READY_DELAY_SECONDS)

    for character in hex_code:
        pydirectinput.write(character)
        time.sleep(COLOR_CHANGE_TYPE_INTERVAL_SECONDS)


def press_hotkey(*keys):
    for key in keys:
        pydirectinput.keyDown(key)
        time.sleep(0.03)

    for key in reversed(keys):
        pydirectinput.keyUp(key)
        time.sleep(0.03)


def set_clipboard_text(text):
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    global_memory_moveable = 0x0002
    clipboard_unicode_text = 13
    encoded_text = text.encode("utf-16-le") + b"\x00\x00"

    for _ in range(10):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("Could not open clipboard for hex input.")

    handle = None
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(global_memory_moveable, len(encoded_text))
        if not handle:
            raise RuntimeError("Could not allocate clipboard memory.")

        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise RuntimeError("Could not lock clipboard memory.")

        ctypes.memmove(pointer, encoded_text, len(encoded_text))
        kernel32.GlobalUnlock(wintypes.HANDLE(handle))

        if not user32.SetClipboardData(clipboard_unicode_text, wintypes.HANDLE(handle)):
            raise RuntimeError("Could not set clipboard text.")

        handle = None
    finally:
        user32.CloseClipboard()


def enter_hex_code(hex_code):
    time.sleep(HEX_INPUT_READY_DELAY_SECONDS)

    press_hotkey("ctrl", "a")
    time.sleep(COLOR_CHANGE_ACTION_DELAY_SECONDS)
    pydirectinput.press("backspace")
    time.sleep(COLOR_CHANGE_ACTION_DELAY_SECONDS)

    if USE_CLIPBOARD_FOR_HEX_INPUT:
        set_clipboard_text(hex_code)
        time.sleep(COLOR_CHANGE_ACTION_DELAY_SECONDS)
        press_hotkey("ctrl", "v")
        time.sleep(HEX_INPUT_AFTER_PASTE_DELAY_SECONDS)
    else:
        type_hex_code(hex_code)


def change_color(hex_code):
    """
    1. Click the "Change Color" button in the game UI.
    2. Double-Click edit hex location
    3. press backspace
    4. Type the hex code with #
    5. press enter
    6. press confirm color change
    """
    hex_code = normalize_hex_code(hex_code)

    click_at(*CHANGE_COLOR_BUTTON_LOCATION, delay=COLOR_CHANGE_CLICK_DELAY_SECONDS)
    time.sleep(COLOR_CHANGE_ACTION_DELAY_SECONDS)

    click_at(*EDIT_HEX_LOCATION, delay=COLOR_CHANGE_CLICK_DELAY_SECONDS, count=2)
    time.sleep(COLOR_CHANGE_ACTION_DELAY_SECONDS)

    enter_hex_code(hex_code)
    time.sleep(COLOR_CHANGE_ACTION_DELAY_SECONDS)

    pydirectinput.press("enter")
    time.sleep(COLOR_CHANGE_ACTION_DELAY_SECONDS)

    click_at(*CONFIRM_COLOR_CHANGE_LOCATION, delay=COLOR_CHANGE_CLICK_DELAY_SECONDS)
    time.sleep(COLOR_CHANGE_ACTION_DELAY_SECONDS)


def is_key_pressed(key_name):
    key_code = VIRTUAL_KEY_CODES[key_name.lower()]
    return ctypes.windll.user32.GetAsyncKeyState(key_code) & 0x8000 != 0


def is_hotkey_pressed(hotkey):
    return all(is_key_pressed(key) for key in hotkey)


def check_pause_hotkey():
    global is_paused, was_pause_hotkey_down

    pause_hotkey_down = is_hotkey_pressed(PAUSE_HOTKEY)
    if pause_hotkey_down and not was_pause_hotkey_down:
        is_paused = not is_paused
        print("Paused. Press the pause hotkey again to resume." if is_paused else "Resumed.")

    was_pause_hotkey_down = pause_hotkey_down


def wait_if_paused():
    while True:
        check_pause_hotkey()
        if not is_paused:
            return
        time.sleep(0.05)


def wait_for_hotkey(hotkey):
    hotkey_text = " + ".join(key.upper() for key in hotkey)
    print(f"Waiting for {hotkey_text} to start painting...")

    while not is_hotkey_pressed(hotkey):
        time.sleep(0.03)

    while is_hotkey_pressed(hotkey):
        time.sleep(0.03)

    print("Started painting.")


def rgb_to_hex(rgb):
    red, green, blue = rgb[:3]
    return f"#{red:02X}{green:02X}{blue:02X}"


def is_white_pixel(rgb):
    red, green, blue = rgb[:3]
    return (
        red >= WHITE_SKIP_MIN_CHANNEL_VALUE
        and green >= WHITE_SKIP_MIN_CHANNEL_VALUE
        and blue >= WHITE_SKIP_MIN_CHANNEL_VALUE
    )


def find_first_image(folder):
    image_paths = [
        path
        for path in sorted(folder.iterdir())
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    ]

    if not image_paths:
        supported_types = ", ".join(sorted(SUPPORTED_IMAGE_EXTENSIONS))
        raise FileNotFoundError(f"No image found in {folder}. Supported types: {supported_types}")

    return image_paths[0]


def load_image(image_path, target_resolution):
    image = Image.open(image_path).convert("RGB")
    image = image.resize(target_resolution, Image.Resampling.LANCZOS)

    if MAX_COLORS is not None:
        image = image.quantize(colors=MAX_COLORS).convert("RGB")

    return image


def get_canvas_metrics():
    canvas_width_pixels, canvas_height_pixels = CANVAS_RESOLUTION
    if canvas_width_pixels <= 0 or canvas_height_pixels <= 0:
        raise ValueError("CANVAS_RESOLUTION must be filled with positive numbers.")

    left_x, top_y = CANVAS_TOP_LEFT
    right_x, bottom_y = CANVAS_BOTTOM_RIGHT
    canvas_width_normal_pixels = right_x - left_x
    canvas_height_normal_pixels = bottom_y - top_y

    if canvas_width_normal_pixels <= 0:
        raise ValueError("CANVAS_BOTTOM_RIGHT must be to the right of CANVAS_TOP_LEFT.")

    if canvas_height_normal_pixels <= 0:
        raise ValueError("CANVAS_BOTTOM_RIGHT must be below CANVAS_TOP_LEFT.")

    drawable_left = left_x + CANVAS_BORDER_INSET_NORMAL_PIXELS
    drawable_top = top_y + CANVAS_BORDER_INSET_NORMAL_PIXELS
    drawable_right = right_x - CANVAS_BORDER_INSET_NORMAL_PIXELS
    drawable_bottom = bottom_y - CANVAS_BORDER_INSET_NORMAL_PIXELS

    return {
        "pixel_width": canvas_width_normal_pixels / canvas_width_pixels,
        "pixel_height": canvas_height_normal_pixels / canvas_height_pixels,
        "left": drawable_left,
        "top": drawable_top,
        "right": drawable_right,
        "bottom": drawable_bottom,
    }


def game_pixel_to_screen(row, column, metrics):
    x = metrics["left"] + ((column + 0.5) * metrics["pixel_width"])
    y = metrics["top"] + ((row + 0.5) * metrics["pixel_height"])
    return round(x), round(y)


def is_inside_canvas(x, y, metrics):
    return metrics["left"] <= x <= metrics["right"] and metrics["top"] <= y <= metrics["bottom"]


def get_paint_row_range():
    _, canvas_height_pixels = CANVAS_RESOLUTION

    if not PAINT_ONLY_SELECTED_LANE:
        return 0, canvas_height_pixels

    if HORIZONTAL_LANE_COUNT <= 0:
        raise ValueError("HORIZONTAL_LANE_COUNT must be a positive number.")

    if not 1 <= HORIZONTAL_LANE_NUMBER <= HORIZONTAL_LANE_COUNT:
        raise ValueError(
            "HORIZONTAL_LANE_NUMBER must be between 1 and "
            f"HORIZONTAL_LANE_COUNT ({HORIZONTAL_LANE_COUNT})."
        )

    row_start = (canvas_height_pixels * (HORIZONTAL_LANE_NUMBER - 1)) // HORIZONTAL_LANE_COUNT
    row_end = (canvas_height_pixels * HORIZONTAL_LANE_NUMBER) // HORIZONTAL_LANE_COUNT

    if row_start == row_end:
        raise ValueError(
            "Selected lane has no rows. Use fewer lanes or a taller CANVAS_RESOLUTION."
        )

    return row_start, row_end


def group_pixels_by_color(image, metrics):
    canvas_width_pixels, canvas_height_pixels = CANVAS_RESOLUTION
    pixels = image.load()
    color_groups = defaultdict(list)
    row_start, row_end = get_paint_row_range()

    for row in range(row_start, row_end, DRAW_STEP):
        for column in range(0, canvas_width_pixels, DRAW_STEP):
            pixel = pixels[column, row]
            if SKIP_WHITE_PIXELS and is_white_pixel(pixel):
                continue

            x, y = game_pixel_to_screen(row, column, metrics)
            if is_inside_canvas(x, y, metrics):
                color_groups[rgb_to_hex(pixel)].append((x, y))

    return color_groups


def paint_image():
    image_path = find_first_image(IMAGE_FOLDER)
    print(f"Using image: {image_path}")

    image = load_image(image_path, CANVAS_RESOLUTION)
    metrics = get_canvas_metrics()
    color_groups = group_pixels_by_color(image, metrics)

    if PAINT_ONLY_SELECTED_LANE:
        row_start, row_end = get_paint_row_range()
        print(
            f"Painting lane {HORIZONTAL_LANE_NUMBER}/{HORIZONTAL_LANE_COUNT} "
            f"(rows {row_start + 1}-{row_end} of {CANVAS_RESOLUTION[1]})."
        )

    print(f"Painting {sum(len(points) for points in color_groups.values())} pixels with {len(color_groups)} colors.")

    for hex_code, points in sorted(color_groups.items(), key=lambda item: len(item[1]), reverse=True):
        wait_if_paused()
        change_color(hex_code)
        for x, y in points:
            wait_if_paused()
            click_at(x, y, delay=CLICK_DELAY_SECONDS)


if __name__ == "__main__":
    wait_for_hotkey(START_HOTKEY)
    paint_image()
