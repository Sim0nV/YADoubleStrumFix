import json
import os
import sys
import queue
import threading
import time
from pathlib import Path

import pygame
import vgamepad as vg
import tkinter as tk
from tkinter import ttk, messagebox


APP_NAME = "YADoubleStrumFix"
APP_VERSION = "1.0.0"
APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "YADoubleStrumFix"
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = APP_DATA_DIR / "config.json"

DEFAULTS = {
    "strum_debounce": 0.015,
    "strum_cooldown": 0.060,
    "poll_rate": 250,
    "whammy_deadzone": -0.95,
    "star_power_threshold": 0.90,
    "debug": False,
}

BUTTON_MAP = {
    0: vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
    1: vg.XUSB_BUTTON.XUSB_GAMEPAD_B,
    2: vg.XUSB_BUTTON.XUSB_GAMEPAD_X,
    3: vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
    4: vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
    6: vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK,
    7: vg.XUSB_BUTTON.XUSB_GAMEPAD_START,
}

STRUM_UP = vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP
STRUM_DOWN = vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN

WHAMMY_AXIS = 1
STAR_POWER_AXIS = 0


def axis_to_trigger(value, minimum=-1.0, maximum=1.0):
    if maximum <= minimum:
        return 0

    normalized = (value - minimum) / (maximum - minimum)
    normalized = max(0.0, min(1.0, normalized))
    return int(normalized * 255)


def load_config():
    config = DEFAULTS.copy()
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            saved = json.load(f)
        for key in DEFAULTS:
            if key in saved:
                config[key] = saved[key]
    except (OSError, ValueError):
        pass
    return config


def save_config(config):
    try:
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except OSError:
        pass


class GuitarWorker:
    """Owns pygame and the virtual controller so the GUI thread stays responsive."""

    def __init__(self, events):
        self.events = events
        self.commands = queue.Queue()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.stop_event = threading.Event()
        self.running = False
        self.selected_index = None
        self.settings = DEFAULTS.copy()
        self.gamepad = None

    def start_thread(self):
        self.thread.start()

    def send(self, command, value=None):
        self.commands.put((command, value))

    def shutdown(self):
        self.stop_event.set()
        self.send("quit")
        if self.thread.is_alive():
            self.thread.join(timeout=2)

    def run(self):
        pygame.init()
        pygame.joystick.init()

        try:
            self.events.put(("status", "ready", "Waiting for a guitar."))
            last_count = -1

            while not self.stop_event.is_set():
                self.process_commands()

                count = pygame.joystick.get_count()
                if count != last_count:
                    last_count = count
                    controllers = []
                    for i in range(count):
                        joystick = pygame.joystick.Joystick(i)
                        joystick.init()
                        controllers.append({
                            "index": i,
                            "name": joystick.get_name(),
                            "buttons": joystick.get_numbuttons(),
                            "axes": joystick.get_numaxes(),
                            "hats": joystick.get_numhats(),
                        })
                    self.events.put(("controllers", controllers))

                if self.running:
                    self.poll_guitar()
                else:
                    pygame.event.pump()
                    time.sleep(0.05)

        except Exception as exc:
            self.events.put(("fatal", str(exc)))
        finally:
            self.release_gamepad()
            pygame.quit()

    def process_commands(self):
        while True:
            try:
                command, value = self.commands.get_nowait()
            except queue.Empty:
                return

            if command == "select":
                self.selected_index = value

            elif command == "start":
                self.settings = value
                self.start_guitar()

            elif command == "stop":
                self.stop_guitar()

            elif command == "quit":
                self.stop_event.set()
                return

    def start_guitar(self):
        if self.selected_index is None:
            self.events.put(("error", "Select a guitar first."))
            return

        try:
            count = pygame.joystick.get_count()
            if self.selected_index >= count:
                self.events.put(("error", "The selected controller is no longer connected."))
                return

            guitar = pygame.joystick.Joystick(self.selected_index)
            guitar.init()

            if guitar.get_numhats() == 0:
                self.events.put(("error", "The selected controller has no hat/strum input."))
                return

            self.guitar = guitar
            self.gamepad = vg.VX360Gamepad()
            self.running = True

            self.raw_strum = None
            self.stable_strum = None
            self.raw_changed_time = time.monotonic()
            self.virtual_strum = None
            self.last_strum_time = -999.0

            self.events.put(("running", guitar.get_name()))
        except Exception as exc:
            self.running = False
            self.release_gamepad()
            self.events.put((
                "driver_error",
                "Could not create the virtual Xbox controller.\n\n"
                "Make sure the ViGEmBus driver is installed.\n\n"
                f"Details: {exc}",
            ))

    def stop_guitar(self):
        self.running = False
        self.release_gamepad()
        self.events.put(("stopped",))

    def release_gamepad(self):
        if self.gamepad is None:
            return

        try:
            for button in BUTTON_MAP.values():
                self.gamepad.release_button(button=button)
            self.gamepad.release_button(button=STRUM_UP)
            self.gamepad.release_button(button=STRUM_DOWN)
            self.gamepad.left_trigger(value=0)
            self.gamepad.right_trigger(value=0)
            self.gamepad.update()
        except Exception:
            pass

        self.gamepad = None

    def poll_guitar(self):
        guitar = self.guitar
        gamepad = self.gamepad
        settings = self.settings

        loop_start = time.perf_counter()
        pygame.event.pump()

        for guitar_button, xbox_button in BUTTON_MAP.items():
            if guitar_button >= guitar.get_numbuttons():
                continue

            if guitar.get_button(guitar_button):
                gamepad.press_button(button=xbox_button)
            else:
                gamepad.release_button(button=xbox_button)

        # Star Power -> Xbox right shoulder.
        if STAR_POWER_AXIS < guitar.get_numaxes():
            star_power = guitar.get_axis(STAR_POWER_AXIS)

            if abs(star_power) > settings["star_power_threshold"]:
                gamepad.press_button(
                    button=vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER
                )
            else:
                gamepad.release_button(
                    button=vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER
                )

        # Strum.
        hat = guitar.get_hat(0)
        if hat[1] > 0:
            current_strum = "up"
        elif hat[1] < 0:
            current_strum = "down"
        else:
            current_strum = None

        now = time.monotonic()

        if current_strum != self.raw_strum:
            self.raw_strum = current_strum
            self.raw_changed_time = now

        if (
            self.raw_strum != self.stable_strum
            and now - self.raw_changed_time >= settings["strum_debounce"]
        ):
            self.stable_strum = self.raw_strum

            if self.stable_strum is None:
                if self.virtual_strum == "up":
                    gamepad.release_button(button=STRUM_UP)
                elif self.virtual_strum == "down":
                    gamepad.release_button(button=STRUM_DOWN)
                self.virtual_strum = None

            elif now - self.last_strum_time >= settings["strum_cooldown"]:
                if self.virtual_strum == "up":
                    gamepad.release_button(button=STRUM_UP)
                elif self.virtual_strum == "down":
                    gamepad.release_button(button=STRUM_DOWN)

                if self.stable_strum == "up":
                    gamepad.press_button(button=STRUM_UP)
                else:
                    gamepad.press_button(button=STRUM_DOWN)

                self.virtual_strum = self.stable_strum
                self.last_strum_time = now

        # Whammy -> left trigger.
        if WHAMMY_AXIS < guitar.get_numaxes():
            whammy = guitar.get_axis(WHAMMY_AXIS)

            if whammy <= settings["whammy_deadzone"]:
                whammy_value = 0
            else:
                whammy_value = axis_to_trigger(
                    whammy,
                    settings["whammy_deadzone"],
                    1.0,
                )

            gamepad.left_trigger(value=whammy_value)
        else:
            gamepad.left_trigger(value=0)

        gamepad.update()

        elapsed = time.perf_counter() - loop_start
        delay = (1.0 / max(1, settings["poll_rate"])) - elapsed
        if delay > 0:
            time.sleep(delay)


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("450x820")
        self.root.minsize(450, 700)

        self.config = load_config()
        self.events = queue.Queue()
        self.worker = GuitarWorker(self.events)
        self.controllers = []
        self.running = False

        self.build_ui()
        self.worker.start_thread()

        self.root.after(50, self.process_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def build_ui(self):
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)

        title = ttk.Label(
            outer,
            text="Yet Another Double Strum Fix",
            font=("Segoe UI", 20, "bold"),
        )
        title.pack(anchor="w")

        subtitle = ttk.Label(
            outer,
            text="Prevent same-direction double strumming on your guitar controller.",
        )
        subtitle.pack(anchor="w", pady=(0, 18))

        controller_frame = ttk.LabelFrame(
            outer,
            text="Guitar Controller",
            padding=12,
        )
        controller_frame.pack(fill="x")

        self.controller_var = tk.StringVar()
        self.controller_combo = ttk.Combobox(
            controller_frame,
            textvariable=self.controller_var,
            state="readonly",
        )
        self.controller_combo.pack(side="left", fill="x", expand=True)
        self.controller_combo.bind("<<ComboboxSelected>>", self.controller_selected)

        self.refresh_button = ttk.Button(
            controller_frame,
            text="Refresh",
            command=lambda: self.worker.send("refresh"),
        )
        self.refresh_button.pack(side="left", padx=(8, 0))

        status_frame = ttk.LabelFrame(
            outer,
            text="Status",
            padding=12,
        )
        status_frame.pack(fill="x", pady=12)

        self.guitar_status = tk.StringVar(value="● Waiting for controller")
        self.virtual_status = tk.StringVar(value="● Virtual Xbox controller: stopped")
        self.detail_status = tk.StringVar(value="")

        ttk.Label(status_frame, textvariable=self.guitar_status).pack(anchor="w")
        ttk.Label(status_frame, textvariable=self.virtual_status).pack(anchor="w")
        ttk.Label(status_frame, textvariable=self.detail_status).pack(
            anchor="w", pady=(6, 0)
        )

        settings = ttk.LabelFrame(
            outer,
            text="Input Settings",
            padding=12,
        )
        settings.pack(fill="x")

        setting_rows = [
            (
                "strum_debounce",
                "Strum Debounce",
                "How long a strum must remain stable before it is recognized.",
            ),
            (
                "strum_cooldown",
                "Strum Cooldown",
                "Minimum time between recognized strums.",
            ),
            (
                "poll_rate",
                "Poll Rate",
                "How often the controller is checked for input.",
            ),
            (
                "whammy_deadzone",
                "Whammy Deadzone",
                "How far the whammy bar must move before input is sent.",
            ),
            (
                "star_power_threshold",
                "Star Power Threshold",
                "How far the guitar must be tilted before Star Power activates.",
            ),
        ]

        self.vars = {}
        self.setting_entries = []
        self.debug_checkbutton = None

        for row, (key, label, description) in enumerate(setting_rows):
            ttk.Label(
                settings,
                text=label,
            ).grid(
                row=row * 2,
                column=0,
                sticky="w",
                pady=(4, 0),
            )

            var = tk.StringVar(value=str(self.config[key]))
            self.vars[key] = var

            entry = ttk.Entry(
                settings,
                textvariable=var,
                width=12,
            )
            entry.grid(
                row=row * 2,
                column=1,
                sticky="e",
                pady=(4, 0),
            )
            self.setting_entries.append(entry)

            ttk.Label(
                settings,
                text=description,
                foreground="#777777",
                wraplength=300,
            ).grid(
                row=row * 2 + 1,
                column=0,
                columnspan=2,
                sticky="w",
                pady=(0, 5),
            )

        self.debug_var = tk.BooleanVar(value=self.config["debug"])

        self.debug_checkbutton = ttk.Checkbutton(
            settings,
            text="Debug Logging",
            variable=self.debug_var,
        )
        self.debug_checkbutton.grid(
            row=len(setting_rows) * 2,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(8, 0),
        )

        ttk.Label(
            settings,
            text="Diagnostic output for troubleshooting. May reduce performance.",
            foreground="#777777",
            wraplength=300,
        ).grid(
            row=len(setting_rows) * 2 + 1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 4),
        )

        settings.columnconfigure(0, weight=1)

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(18, 0))

        self.start_button = ttk.Button(
            buttons,
            text="Start",
            command=self.start,
        )
        self.start_button.pack(side="left")

        self.stop_button = ttk.Button(
            buttons,
            text="Stop",
            command=self.stop,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=8)

        self.mapping_button = ttk.Button(
            buttons,
            text="Controller Mapping",
            command=self.show_controller_mapping,
        )
        self.mapping_button.pack(side="left", padx=8)

        self.save_settings_button = ttk.Button(
            buttons,
            text="Save Settings",
            command=self.save_settings,
        )
        self.save_settings_button.pack(side="right")

        footer = ttk.Label(
            outer,
            text=f"by Sim0nV  •  v{APP_VERSION}",
            foreground="#777777",
        )
        footer.pack(side="bottom", anchor="e", pady=(12, 0))

    def show_controller_mapping(self):
        window = tk.Toplevel(self.root)
        window.title("Controller Mapping")
        window.resizable(False, False)
        window.transient(self.root)
        window.grab_set()

        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Controller Mapping",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", pady=(0, 12))

        mapping = [
            ("Green", "A"),
            ("Red", "B"),
            ("Yellow", "X"),
            ("Blue", "Y"),
            ("Orange", "LB"),
            ("Select", "Back"),
            ("Start", "Start"),
            ("Strum Up", "D-pad Up"),
            ("Strum Down", "D-pad Down"),
            ("Whammy", "Right Trigger"),
            ("Tilt / Star Power", "RB"),
        ]

        table = ttk.Frame(frame)
        table.pack(fill="x")

        ttk.Label(
            table,
            text="Guitar Input",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 40), pady=(0, 6))

        ttk.Label(
            table,
            text="Virtual Xbox 360",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=1, sticky="w", pady=(0, 6))

        ttk.Separator(table, orient="horizontal").grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 6),
        )

        for row, (guitar_input, xbox_input) in enumerate(mapping, start=2):
            ttk.Label(
                table,
                text=guitar_input,
            ).grid(row=row, column=0, sticky="w", pady=3)

            ttk.Label(
                table,
                text=xbox_input,
            ).grid(row=row, column=1, sticky="w", pady=3)

        ttk.Button(
            frame,
            text="Close",
            command=window.destroy,
        ).pack(anchor="e", pady=(14, 0))

        window.update_idletasks()

        width = window.winfo_reqwidth()
        height = window.winfo_reqheight()
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()

        x = (screen_width - width) // 2
        y = (screen_height - height) // 2

        window.geometry(f"{width}x{height}+{x}+{y}")
        
    def controller_selected(self, _event=None):
        index = self.controller_combo.current()
        if 0 <= index < len(self.controllers):
            self.worker.send("select", self.controllers[index]["index"])
            self.guitar_status.set(
                f"● Selected: {self.controllers[index]['name']}"
            )

    def get_settings(self):
        try:
            settings = {
                "strum_debounce": float(self.vars["strum_debounce"].get()),
                "strum_cooldown": float(self.vars["strum_cooldown"].get()),
                "poll_rate": int(self.vars["poll_rate"].get()),
                "whammy_deadzone": float(self.vars["whammy_deadzone"].get()),
                "star_power_threshold": float(
                    self.vars["star_power_threshold"].get()
                ),
                "debug": self.debug_var.get(),
            }

            if not 0 <= settings["strum_debounce"] <= 1:
                raise ValueError("Strum debounce must be between 0 and 1.")

            if not 0 <= settings["strum_cooldown"] <= 1:
                raise ValueError("Strum cooldown must be between 0 and 1.")

            if settings["poll_rate"] <= 0:
                raise ValueError("Poll rate must be greater than zero.")

            if not -1 <= settings["whammy_deadzone"] < 1:
                raise ValueError("Whammy deadzone must be between -1 and 1.")

            if 0 < settings["star_power_threshold"] <= 1:
                return settings

            raise ValueError("Star Power threshold must be greater than 0 and at most 1.")

        except ValueError as exc:
            messagebox.showerror("Invalid Settings", str(exc))
            return None

    def save_settings(self):
        settings = self.get_settings()
        if settings is None:
            return

        self.config = settings
        save_config(settings)
        self.detail_status.set(f"Settings saved to:\n{CONFIG_FILE}")

    def start(self):
        if not self.controllers:
            messagebox.showwarning(
                "No Controller",
                "Connect your guitar controller and click Refresh.",
            )
            return

        if self.controller_combo.current() < 0:
            messagebox.showwarning(
                "No Controller",
                "Select your guitar controller first.",
            )
            return

        settings = self.get_settings()
        if settings is None:
            return

        self.config = settings
        save_config(settings)
        self.worker.send("start", settings)

    def stop(self):
        self.worker.send("stop")

    def process_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]

                if kind == "controllers":
                    self.controllers = event[1]
                    names = [
                        f"{c['name']}  "
                        f"({c['buttons']} buttons, {c['axes']} axes, {c['hats']} hats)"
                        for c in self.controllers
                    ]
                    self.controller_combo["values"] = names

                    if names and self.controller_combo.current() < 0:
                        self.controller_combo.current(0)
                        self.controller_selected()

                    if not names:
                        self.guitar_status.set("● No controllers detected")

                elif kind == "running":
                    self.running = True
                    self.guitar_status.set(f"● Guitar connected: {event[1]}")
                    self.virtual_status.set("● Virtual Xbox 360 controller: ACTIVE")
                    self.detail_status.set(
                        "In YARG: Use Xbox Controller as the device and bind Star Power to RB,\n"
                        "then disable other profiles using the non-virtual controller as necessary.\n"
                        "You may have to remove and re-add the Xbox Controller to your profile."
                    )
                    self.start_button.configure(state="disabled")
                    self.stop_button.configure(state="normal")
                    self.controller_combo.configure(state="disabled")
                    self.refresh_button.configure(state="disabled")
                    for entry in self.setting_entries:
                        entry.configure(state="disabled")
                    if self.debug_checkbutton:
                        self.debug_checkbutton.configure(state="disabled")
                    self.save_settings_button.configure(state="disabled")
                    self.mapping_button.configure(state="disabled")

                elif kind == "stopped":
                    self.running = False
                    self.virtual_status.set("● Virtual Xbox controller: stopped")
                    self.detail_status.set("")
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.controller_combo.configure(state="readonly")
                    self.refresh_button.configure(state="normal")
                    for entry in self.setting_entries:
                        entry.configure(state="normal")
                    if self.debug_checkbutton:
                        self.debug_checkbutton.configure(state="normal")
                    self.save_settings_button.configure(state="normal")
                    self.mapping_button.configure(state="normal")

                elif kind == "ready":
                    self.detail_status.set(event[2])

                elif kind == "error":
                    messagebox.showerror("YADoubleStrumFix", event[1])

                elif kind == "driver_error":
                    self.running = False
                    self.virtual_status.set("● Virtual Xbox controller: unavailable")
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.controller_combo.configure(state="readonly")
                    self.refresh_button.configure(state="normal")
                    for entry in self.setting_entries:
                        entry.configure(state="normal")
                    if self.debug_checkbutton:
                        self.debug_checkbutton.configure(state="normal")
                    self.save_settings_button.configure(state="normal")
                    self.mapping_button.configure(state="normal")
                    messagebox.showerror("Virtual Controller Error", event[1])

                elif kind == "fatal":
                    messagebox.showerror("Fatal Error", event[1])

        except queue.Empty:
            pass

        self.root.after(50, self.process_events)

    def close(self):
        self.worker.shutdown()
        self.root.destroy()

def resource_path(filename):
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, filename)

    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)

def main():
    root = tk.Tk()
    root.iconbitmap(resource_path("icon.ico"))

    # A simple Windows-friendly ttk theme.
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass

    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
