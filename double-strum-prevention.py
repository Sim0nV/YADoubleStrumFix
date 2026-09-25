import sys
import time

import pygame
import vgamepad as vg


# ============================================================
# CONFIGURATION
# ============================================================

POLL_RATE = 250

# Strum filtering.
STRUM_DEBOUNCE = 0.015
STRUM_COOLDOWN = 0.060

# Guitar axes.
WHAMMY_AXIS = 1
STAR_POWER_AXIS = 0

# Whammy:
# Physical released position should be around -1.0.
# Anything below this threshold is treated as completely released.
WHAMMY_DEADZONE = -0.95

# Star Power:
# Entire physical axis range is sent to the Xbox trigger.
#
# -1.0 = 0
#  0.0 = ~128
# +1.0 = 255
#
# Change these if your controller's actual resting/maximum
# values don't reach the full -1..+1 range.
STAR_POWER_MIN = -1.0
STAR_POWER_MAX = 1.0
STAR_POWER_THRESHOLD = 0.9

DEBUG = False


# ============================================================
# XBOX CONTROLLER MAPPING
# ============================================================

BUTTON_MAP = {
    0: vg.XUSB_BUTTON.XUSB_GAMEPAD_A,              # Green
    1: vg.XUSB_BUTTON.XUSB_GAMEPAD_B,              # Red
    2: vg.XUSB_BUTTON.XUSB_GAMEPAD_X,              # Yellow
    3: vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,              # Blue
    4: vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,  # Orange
    6: vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK,            # Select
    7: vg.XUSB_BUTTON.XUSB_GAMEPAD_START,           # Start
}

STRUM_UP = vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP
STRUM_DOWN = vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN


# ============================================================
# AXIS MAPPING
# ============================================================

def axis_to_trigger(value, minimum=-1.0, maximum=1.0):
    """
    Convert a pygame axis value to an XInput trigger value.

    pygame:
        -1.0 .. +1.0

    XInput:
        0 .. 255
    """

    if maximum <= minimum:
        return 0

    normalized = (
        (value - minimum)
        / (maximum - minimum)
    )

    normalized = max(
        0.0,
        min(1.0, normalized)
    )

    return int(normalized * 255)


# ============================================================
# FIND GUITAR
# ============================================================

def find_guitar():
    pygame.joystick.init()

    count = pygame.joystick.get_count()

    print(f"Found {count} joystick(s):")

    for i in range(count):
        joystick = pygame.joystick.Joystick(i)
        joystick.init()

        print(
            f"  [{i}] {joystick.get_name()} "
            f"(buttons={joystick.get_numbuttons()}, "
            f"axes={joystick.get_numaxes()}, "
            f"hats={joystick.get_numhats()})"
        )

    if count == 0:
        print()
        print("No controllers found.")
        sys.exit(1)

    print()
    print("Strum the guitar to select it...")

    while True:
        pygame.event.pump()

        for i in range(count):
            joystick = pygame.joystick.Joystick(i)

            if joystick.get_numhats() > 0:
                if joystick.get_hat(0) != (0, 0):
                    print()
                    print(
                        f"Using controller [{i}]: "
                        f"{joystick.get_name()}"
                    )
                    return joystick

        time.sleep(1 / POLL_RATE)


# ============================================================
# MAIN
# ============================================================

def main():
    pygame.init()

    guitar = find_guitar()

    gamepad = vg.VX360Gamepad()

    print()
    print("Virtual Xbox 360 controller created.")
    print("Guitar is ready for YARG.")
    print("Press Ctrl+C to quit.")
    print()

    # ========================================================
    # STRUM STATE
    # ========================================================

    raw_strum = None
    stable_strum = None

    raw_changed_time = time.monotonic()

    virtual_strum = None

    last_strum_time = -999.0

    # ========================================================
    # MAIN LOOP
    # ========================================================

    try:
        while True:

            loop_start = time.perf_counter()

            pygame.event.pump()

            # =================================================
            # FRET BUTTONS
            # =================================================

            for guitar_button, xbox_button in BUTTON_MAP.items():

                if guitar_button >= guitar.get_numbuttons():
                    continue

                if guitar.get_button(guitar_button):
                    gamepad.press_button(
                        button=xbox_button
                    )
                else:
                    gamepad.release_button(
                        button=xbox_button
                    )

            # =================================================
            # TILT / STAR POWER
            # =================================================

            if STAR_POWER_AXIS < guitar.get_numaxes():

                star_power = guitar.get_axis(
                    STAR_POWER_AXIS
                )

                # Axis 0:
                # Released  ~= negative / near 0
                # Tilted    ~= +1.0
                #
                # Turn the tilt into a normal Xbox button press.

                if abs(star_power) > STAR_POWER_THRESHOLD:

                    gamepad.press_button(
                        button=vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER
                    )

                else:

                    gamepad.release_button(
                        button=vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER
                    )

            else:

                gamepad.release_button(
                    button=vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER
                )
    
            # =================================================
            # READ RAW STRUM
            # =================================================

            if guitar.get_numhats() > 0:
                hat = guitar.get_hat(0)
            else:
                hat = (0, 0)

            if hat[1] > 0:
                current_strum = "up"

            elif hat[1] < 0:
                current_strum = "down"

            else:
                current_strum = None

            now = time.monotonic()

            # =================================================
            # RAW STATE CHANGE
            # =================================================

            if current_strum != raw_strum:

                raw_strum = current_strum
                raw_changed_time = now

                if DEBUG:
                    print(
                        f"\nRAW -> {raw_strum}"
                    )

            # =================================================
            # DEBOUNCE
            # =================================================

            if (
                raw_strum != stable_strum
                and
                now - raw_changed_time >= STRUM_DEBOUNCE
            ):

                old_stable = stable_strum
                stable_strum = raw_strum

                if DEBUG:
                    print(
                        f"STABLE: "
                        f"{old_stable} -> "
                        f"{stable_strum}"
                    )

                # =============================================
                # RELEASE
                # =============================================

                if stable_strum is None:

                    if virtual_strum == "up":

                        gamepad.release_button(
                            button=STRUM_UP
                        )

                    elif virtual_strum == "down":

                        gamepad.release_button(
                            button=STRUM_DOWN
                        )

                    virtual_strum = None

                # =============================================
                # NEW STRUM
                # =============================================

                else:

                    if (
                        now - last_strum_time
                        >= STRUM_COOLDOWN
                    ):

                        # Release previous strum.

                        if virtual_strum == "up":

                            gamepad.release_button(
                                button=STRUM_UP
                            )

                        elif virtual_strum == "down":

                            gamepad.release_button(
                                button=STRUM_DOWN
                            )

                        # Press new strum.

                        if stable_strum == "up":

                            gamepad.press_button(
                                button=STRUM_UP
                            )

                        elif stable_strum == "down":

                            gamepad.press_button(
                                button=STRUM_DOWN
                            )

                        virtual_strum = stable_strum
                        last_strum_time = now

                        if DEBUG:
                            print(
                                f"ACCEPTED: "
                                f"{stable_strum}"
                            )

            # =================================================
            # WHAMMY
            # =================================================

            if WHAMMY_AXIS < guitar.get_numaxes():

                whammy = guitar.get_axis(
                    WHAMMY_AXIS
                )

                # Your diagnostic showed:
                #
                # released ~= -1.0
                # pressed   -> +1.0
                #
                # Treat the bottom end as completely released.

                if whammy <= WHAMMY_DEADZONE:

                    whammy_value = 0

                else:

                    whammy_value = axis_to_trigger(
                        whammy,
                        WHAMMY_DEADZONE,
                        1.0
                    )

                gamepad.left_trigger(
                    value=whammy_value
                )

                # if DEBUG:
                    # print(
                    #     f"\nWhammy: "
                    #     f"{whammy:+.3f} "
                    #     f"-> {whammy_value:3d}"
                    # )

            else:

                gamepad.left_trigger(
                    value=0
                )

            # =================================================
            # UPDATE CONTROLLER
            # =================================================

            gamepad.update()

            # =================================================
            # POLL
            # =================================================

            elapsed = (
                time.perf_counter() - loop_start
            )

            delay = (
                1.0 / POLL_RATE
            ) - elapsed

            if delay > 0:
                time.sleep(delay)

    except KeyboardInterrupt:

        print()
        print("Stopping...")

    finally:

        # RELEASE BUTTONS

        for xbox_button in BUTTON_MAP.values():
            gamepad.release_button(
                button=xbox_button
            )

        gamepad.release_button(
            button=STRUM_UP
        )

        gamepad.release_button(
            button=STRUM_DOWN
        )

        # RELEASE TRIGGERS

        gamepad.left_trigger(
            value=0
        )

        gamepad.right_trigger(
            value=0
        )

        gamepad.update()

        pygame.quit()


if __name__ == "__main__":
    main()
