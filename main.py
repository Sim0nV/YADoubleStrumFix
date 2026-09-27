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
APP_VERSION = "1.1.0"
APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "YADoubleStrumFix"
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = APP_DATA_DIR / "config.json"

DEFAULTS = {
    "strum_debounce": 0.015,
    "strum_cooldown": 0.060,
    "poll_rate": 250,
    "mapping": {
        "green_button": 0,
        "red_button": 1,
        "yellow_button": 2,
        "blue_button": 3,
        "orange_button": 4,
        "select_button": 6,
        "start_button": 7,
        "strum_hat": 0,
        "strum_up_val": 1,
        "strum_down_val": -1,
        "whammy_axis": 1,
        "whammy_deadzone": -0.95,
        "star_power_axis": 0,
        "star_power_threshold": 0.90,
        "green_xbox": "A",
        "red_xbox": "B",
        "yellow_xbox": "X",
        "blue_xbox": "Y",
        "orange_xbox": "LB",
        "select_xbox": "Back",
        "start_xbox": "Start",
        "whammy_xbox": "Right Trigger",
        "star_power_xbox": "RB",
        "strum_up_xbox": "D-pad Up",
        "strum_down_xbox": "D-pad Down",
    }
}

XBOX_BUTTON_MAP = {
    "A": vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
    "B": vg.XUSB_BUTTON.XUSB_GAMEPAD_B,
    "X": vg.XUSB_BUTTON.XUSB_GAMEPAD_X,
    "Y": vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
    "LB": vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
    "RB": vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
    "Back": vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK,
    "Start": vg.XUSB_BUTTON.XUSB_GAMEPAD_START,
    "D-pad Up": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
    "D-pad Down": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
    "D-pad Left": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
    "D-pad Right": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
}

AVAILABLE_XBOX_BUTTONS = list(XBOX_BUTTON_MAP.keys())
AVAILABLE_XBOX_TRIGGERS = ["Left Trigger", "Right Trigger", "None"]

TOOLTIPS = {
    "green_button": "Physical button index on your guitar controller for the Green fret.",
    "red_button": "Physical button index on your guitar controller for the Red fret.",
    "yellow_button": "Physical button index on your guitar controller for the Yellow fret.",
    "blue_button": "Physical button index on your guitar controller for the Blue fret.",
    "orange_button": "Physical button index on your guitar controller for the Orange fret.",
    "select_button": "Physical button index for the Select / Back button.",
    "start_button": "Physical button index for the Start button.",
    "strum_hat": "Hat index used for strumming (usually Hat 0).",
    "strum_up_val": "Axis value from the hat representing Strum Up (e.g. 1).",
    "strum_down_val": "Axis value from the hat representing Strum Down (e.g. -1).",
    "whammy_axis": "Joystick axis index assigned to the Whammy bar.",
    "whammy_deadzone": "Threshold below which whammy movement is ignored (fully released).",
    "star_power_axis": "Joystick axis index assigned to guitar tilt / Star Power.",
    "star_power_threshold": "Tilt threshold above which Star Power triggers.",
}


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<ButtonPress>", self.leave)

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(500, self.showtip)

    def unschedule(self):
        id_ = self.id
        self.id = None
        if id_:
            self.widget.after_cancel(id_)

    def showtip(self, event=None):
        if self.tipwindow or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            font=("Segoe UI", 9),
            padx=6,
            pady=4,
        )
        label.pack(fill=tk.BOTH, expand=True)

    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()


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
                if key == "mapping":
                    config["mapping"] = DEFAULTS["mapping"].copy()
                    if isinstance(saved["mapping"], dict):
                        config["mapping"].update(saved["mapping"])
                else:
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
        self.last_monitor_time = 0.0
        self.settings = DEFAULTS.copy()
        self.gamepad = None
        self.guitar = None

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

                if self.selected_index is not None and self.selected_index < count:
                    now = time.monotonic()
                    if now - self.last_monitor_time >= 0.05:  # ~20 Hz
                        self.last_monitor_time = now
                        try:
                            active_guitar = pygame.joystick.Joystick(self.selected_index)
                            active_guitar.init()
                            pygame.event.pump()
                            buttons_state = {}
                            for b_idx in range(active_guitar.get_numbuttons()):
                                buttons_state[b_idx] = bool(active_guitar.get_button(b_idx))
                            axes_state = {}
                            for a_idx in range(active_guitar.get_numaxes()):
                                axes_state[a_idx] = round(active_guitar.get_axis(a_idx), 3)
                            hats_state = {}
                            for h_idx in range(active_guitar.get_numhats()):
                                hats_state[h_idx] = active_guitar.get_hat(h_idx)
                            self.events.put(("input_log", buttons_state, axes_state, hats_state))
                        except Exception:
                            pass

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
            for btn_name in XBOX_BUTTON_MAP.values():
                try:
                    self.gamepad.release_button(button=btn_name)
                except Exception:
                    pass
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
        mapping = settings.get("mapping", DEFAULTS["mapping"])

        loop_start = time.perf_counter()

        fret_keys = [
            ("green_button", "green_xbox"),
            ("red_button", "red_xbox"),
            ("yellow_button", "yellow_xbox"),
            ("blue_button", "blue_xbox"),
            ("orange_button", "orange_xbox"),
            ("select_button", "select_xbox"),
            ("start_button", "start_xbox"),
        ]

        for b_key, x_key in fret_keys:
            b_idx = mapping.get(b_key)
            x_name = mapping.get(x_key)
            if b_idx is not None and 0 <= b_idx < guitar.get_numbuttons():
                xbox_btn = XBOX_BUTTON_MAP.get(x_name)
                if xbox_btn is not None:
                    if guitar.get_button(b_idx):
                        gamepad.press_button(button=xbox_btn)
                    else:
                        gamepad.release_button(button=xbox_btn)

        # Star Power axis / button
        sp_axis = mapping.get("star_power_axis")
        sp_xbox = mapping.get("star_power_xbox")
        sp_threshold = mapping.get("star_power_threshold", 0.90)
        if sp_axis is not None and 0 <= sp_axis < guitar.get_numaxes():
            star_power = guitar.get_axis(sp_axis)
            sp_btn = XBOX_BUTTON_MAP.get(sp_xbox)
            if sp_btn is not None:
                if abs(star_power) > sp_threshold:
                    gamepad.press_button(button=sp_btn)
                else:
                    gamepad.release_button(button=sp_btn)

        # Strum (Hat)
        strum_hat_idx = mapping.get("strum_hat", 0)
        up_val = mapping.get("strum_up_val", 1)
        down_val = mapping.get("strum_down_val", -1)

        hat = guitar.get_hat(strum_hat_idx) if strum_hat_idx < guitar.get_numhats() else (0, 0)
        if hat[1] == up_val or hat[0] == up_val:
            current_strum = "up"
        elif hat[1] == down_val or hat[0] == down_val:
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
            up_name = mapping.get("strum_up_xbox", "D-pad Up")
            down_name = mapping.get("strum_down_xbox", "D-pad Down")
            up_btn = XBOX_BUTTON_MAP.get(up_name)
            down_btn = XBOX_BUTTON_MAP.get(down_name)

            if self.stable_strum is None:
                if self.virtual_strum == "up" and up_btn is not None:
                    gamepad.release_button(button=up_btn)
                elif self.virtual_strum == "down" and down_btn is not None:
                    gamepad.release_button(button=down_btn)
                self.virtual_strum = None

            elif now - self.last_strum_time >= settings["strum_cooldown"]:
                if self.virtual_strum == "up" and up_btn is not None:
                    gamepad.release_button(button=up_btn)
                elif self.virtual_strum == "down" and down_btn is not None:
                    gamepad.release_button(button=down_btn)

                if self.stable_strum == "up" and up_btn is not None:
                    gamepad.press_button(button=up_btn)
                elif self.stable_strum == "down" and down_btn is not None:
                    gamepad.press_button(button=down_btn)

                self.virtual_strum = self.stable_strum
                self.last_strum_time = now

        # Whammy axis -> trigger
        whammy_axis = mapping.get("whammy_axis")
        whammy_target = mapping.get("whammy_xbox", "Right Trigger")
        whammy_deadzone = mapping.get("whammy_deadzone", -0.95)
        if whammy_axis is not None and 0 <= whammy_axis < guitar.get_numaxes():
            whammy = guitar.get_axis(whammy_axis)

            if whammy <= whammy_deadzone:
                whammy_value = 0
            else:
                whammy_value = axis_to_trigger(
                    whammy,
                    whammy_deadzone,
                    1.0,
                )

            if whammy_target == "Left Trigger":
                gamepad.left_trigger(value=whammy_value)
                gamepad.right_trigger(value=0)
            elif whammy_target == "Right Trigger":
                gamepad.right_trigger(value=whammy_value)
                gamepad.left_trigger(value=0)
            else:
                gamepad.left_trigger(value=0)
                gamepad.right_trigger(value=0)
        else:
            gamepad.left_trigger(value=0)
            gamepad.right_trigger(value=0)

        gamepad.update()

        elapsed = time.perf_counter() - loop_start
        delay = (1.0 / max(1, settings["poll_rate"])) - elapsed
        if delay > 0:
            time.sleep(delay)


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("450x630")
        self.root.minsize(450, 630)

        self.config = load_config()
        self.events = queue.Queue()
        self.worker = GuitarWorker(self.events)
        self.controllers = []
        self.running = False
        self.mapping_window = None

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
        subtitle.pack(anchor="w", pady=(0, 14))

        controller_frame = ttk.LabelFrame(
            outer,
            text="Guitar Controller",
            padding=12,
        )
        controller_frame.pack(fill="x", pady=(0, 10))

        self.controller_var = tk.StringVar()
        self.controller_combo = ttk.Combobox(
            controller_frame,
            textvariable=self.controller_var,
            state="readonly",
        )
        self.controller_combo.pack(side="left", fill="x", expand=True)
        self.controller_combo.bind("<<ComboboxSelected>>", self.controller_selected)
        self.controller_combo.bind("<MouseWheel>", lambda e: "break")
        self.controller_combo.bind("<Button-4>", lambda e: "break")
        self.controller_combo.bind("<Button-5>", lambda e: "break")

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
        status_frame.pack(fill="x", pady=(0, 10))

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
        settings.pack(fill="x", pady=(0, 10))

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
        ]

        self.vars = {}
        self.setting_entries = []

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
                wraplength=380,
            ).grid(
                row=row * 2 + 1,
                column=0,
                columnspan=2,
                sticky="w",
                pady=(0, 5),
            )

        settings.columnconfigure(0, weight=1)

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(18, 0))

        self.mapping_button = ttk.Button(
            buttons,
            text="Controller Mapping/Calibration",
            command=self.show_controller_mapping,
        )
        self.mapping_button.pack(side="right")

        self.setting_entries.append(self.mapping_button)

        save_reset_frame = ttk.Frame(outer)
        save_reset_frame.pack(fill="x", pady=(10, 0))

        self.start_button = ttk.Button(
            save_reset_frame,
            text="Start",
            command=self.start,
        )
        self.start_button.pack(side="left")

        self.stop_button = ttk.Button(
            save_reset_frame,
            text="Stop",
            command=self.stop,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=8)

        self.save_settings_button = ttk.Button(
            save_reset_frame,
            text="Save Settings",
            command=self.save_settings,
        )
        self.save_settings_button.pack(side="right")

        self.reset_button = ttk.Button(
            save_reset_frame,
            text="Reset to Defaults",
            command=self.reset_defaults,
        )
        self.reset_button.pack(side="right", padx=8)
        self.setting_entries.append(self.reset_button)

        footer = ttk.Label(
            outer,
            text=f"by Sim0nV  •  v{APP_VERSION}",
            foreground="#777777",
        )
        footer.pack(side="bottom", anchor="e", pady=(12, 0))

    def show_controller_mapping(self):
        if self.mapping_window is not None and self.mapping_window.winfo_exists():
            self.mapping_window.lift()
            return

        window = tk.Toplevel(self.root)
        window.title("Controller Mapping/Calibration")
        window.resizable(False, False)
        window.transient(self.root)
        try:
            window.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass
        self.mapping_window = window

        def on_close():
            window.destroy()
            self.mapping_window = None

        window.protocol("WM_DELETE_WINDOW", on_close)

        main_frame = ttk.Frame(window, padding=16)
        main_frame.pack(fill="both", expand=True)

        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        ttk.Label(
            left_frame,
            text="Controller Mapping/Calibration",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", pady=(0, 12))

        canvas = tk.Canvas(left_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        mapping_fields = [
            ("Green Fret Button ID", "green_button", "green_xbox", "button"),
            ("Red Fret Button ID", "red_button", "red_xbox", "button"),
            ("Yellow Fret Button ID", "yellow_button", "yellow_xbox", "button"),
            ("Blue Fret Button ID", "blue_button", "blue_xbox", "button"),
            ("Orange Fret Button ID", "orange_button", "orange_xbox", "button"),
            ("Select Button ID", "select_button", "select_xbox", "button"),
            ("Start Button ID", "start_button", "start_xbox", "button"),
            ("Strum Hat ID", "strum_hat", None, "hat_id"),
            ("Strum Up Hat Value", "strum_up_val", "strum_up_xbox", "hat_val"),
            ("Strum Down Hat Value", "strum_down_val", "strum_down_xbox", "hat_val"),
            ("Whammy Axis ID", "whammy_axis", "whammy_xbox", "axis_whammy"),
            ("Whammy Deadzone", "whammy_deadzone", None, "deadzone"),
            ("Star Power Axis ID", "star_power_axis", "star_power_xbox", "axis_sp"),
            ("Star Power Threshold", "star_power_threshold", None, "threshold"),
        ]

        current_mapping = self.config.get("mapping", DEFAULTS["mapping"])
        self.mapping_vars = {}

        ttk.Label(scrollable_frame, text="Setting / Input", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 20), pady=(0, 6))
        ttk.Label(scrollable_frame, text="Guitar ID / Val", font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w", padx=(0, 20), pady=(0, 6))
        ttk.Label(scrollable_frame, text="Xbox Output", font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="w", pady=(0, 6))

        for row_idx, (label_name, idx_key, xbox_key, input_type) in enumerate(mapping_fields, start=1):
            lbl = ttk.Label(scrollable_frame, text=label_name)
            lbl.grid(row=row_idx, column=0, sticky="w", padx=(0, 20), pady=3)

            tip_text = None
            if idx_key and idx_key in TOOLTIPS:
                tip_text = TOOLTIPS[idx_key]
            elif xbox_key and xbox_key in TOOLTIPS:
                tip_text = TOOLTIPS[xbox_key]
            else:
                tip_text = TOOLTIPS.get(label_name.lower().replace(" ", "_"), f"Configuration for {label_name}.")

            if tip_text:
                ToolTip(lbl, tip_text)

            if idx_key is not None:
                if idx_key in current_mapping:
                    val_str = str(current_mapping[idx_key])
                elif idx_key == "whammy_deadzone":
                    val_str = str(current_mapping.get("whammy_deadzone", DEFAULTS["mapping"]["whammy_deadzone"]))
                elif idx_key == "star_power_threshold":
                    val_str = str(current_mapping.get("star_power_threshold", DEFAULTS["mapping"]["star_power_threshold"]))
                elif idx_key == "strum_hat":
                    val_str = str(current_mapping.get("strum_hat", 0))
                elif idx_key == "strum_up_val":
                    val_str = str(current_mapping.get("strum_up_val", 1))
                elif idx_key == "strum_down_val":
                    val_str = str(current_mapping.get("strum_down_val", -1))
                else:
                    val_str = "0"
                self.mapping_vars[idx_key] = tk.StringVar(value=val_str)
                entry = ttk.Entry(scrollable_frame, textvariable=self.mapping_vars[idx_key], width=8)
                entry.grid(row=row_idx, column=1, sticky="w", padx=(0, 20), pady=3)
                if tip_text:
                    ToolTip(entry, tip_text)
            else:
                ttk.Label(scrollable_frame, text="").grid(row=row_idx, column=1, sticky="w", padx=(0, 20), pady=3)

            if xbox_key is not None:
                self.mapping_vars[xbox_key] = tk.StringVar(value=str(current_mapping.get(xbox_key, "")))
                if "whammy" in xbox_key:
                    combo = ttk.Combobox(scrollable_frame, textvariable=self.mapping_vars[xbox_key], values=AVAILABLE_XBOX_TRIGGERS, state="readonly", width=14)
                else:
                    combo = ttk.Combobox(scrollable_frame, textvariable=self.mapping_vars[xbox_key], values=AVAILABLE_XBOX_BUTTONS, state="readonly", width=14)
                combo.grid(row=row_idx, column=2, sticky="w", pady=3)
                combo.bind("<MouseWheel>", lambda e: "break")
                combo.bind("<Button-4>", lambda e: "break")
                combo.bind("<Button-5>", lambda e: "break")
                if tip_text:
                    ToolTip(combo, tip_text)
            else:
                ttk.Label(scrollable_frame, text="").grid(row=row_idx, column=2, sticky="w", pady=3)

        # Right side: Live Input Monitor
        right_frame = ttk.LabelFrame(main_frame, text="Live Guitar Inputs Monitor", padding=10)
        right_frame.pack(side="right", fill="both", expand=False)

        self.input_log_text = tk.Text(right_frame, width=32, height=22, state="disabled", wrap="none", font=("Consolas", 9))
        self.input_log_text.pack(side="left", fill="both", expand=True)
        log_scroll = ttk.Scrollbar(right_frame, orient="vertical", command=self.input_log_text.yview)
        log_scroll.pack(side="right", fill="y")
        self.input_log_text.configure(yscrollcommand=log_scroll.set)

        btn_frame = ttk.Frame(window, padding=16)
        btn_frame.pack(fill="x", side="bottom")

        ttk.Button(
            btn_frame,
            text="Save Mapping",
            command=lambda: self.save_mapping_from_window(window),
        ).pack(side="left")

        ttk.Button(
            btn_frame,
            text="Close",
            command=on_close,
        ).pack(side="right")

        window.update_idletasks()
        width = 720
        height = 600
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.minsize(680, 500)

    def save_mapping_from_window(self, window):
        try:
            new_mapping = self.config.get("mapping", DEFAULTS["mapping"]).copy()
            for key, var in self.mapping_vars.items():
                val = var.get()
                if key.endswith("_button") or key.endswith("_axis") or key == "strum_hat" or key.endswith("_val"):
                    new_mapping[key] = int(val)
                elif key in ("whammy_deadzone", "star_power_threshold"):
                    new_mapping[key] = float(val)
                else:
                    new_mapping[key] = val

            self.config["mapping"] = new_mapping
            save_config(self.config)
            messagebox.showinfo("Success", "Controller mapping saved successfully!", parent=window)
        except ValueError as exc:
            messagebox.showerror("Invalid Input", f"Please enter valid numeric indices for buttons/axes.\nDetails: {exc}", parent=window)

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
                "mapping": self.config.get("mapping", DEFAULTS["mapping"]),
            }

            if not 0 <= settings["strum_debounce"] <= 1:
                raise ValueError("Strum debounce must be between 0 and 1.")

            if not 0 <= settings["strum_cooldown"] <= 1:
                raise ValueError("Strum cooldown must be between 0 and 1.")

            if settings["poll_rate"] <= 0:
                raise ValueError("Poll rate must be greater than zero.")

            return settings

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

    def reset_defaults(self):
        if not messagebox.askyesno("Reset to Defaults", "Are you sure you want to reset all settings and mappings to default values?"):
            return

        self.config = DEFAULTS.copy()
        self.config["mapping"] = DEFAULTS["mapping"].copy()
        save_config(self.config)

        for key, var in self.vars.items():
            if key in DEFAULTS:
                var.set(str(DEFAULTS[key]))

        self.detail_status.set("Settings reset to defaults.")

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

                elif kind == "input_log":
                    if self.mapping_window is not None and self.mapping_window.winfo_exists() and hasattr(self, "input_log_text"):
                        buttons_state, axes_state, hats_state = event[1], event[2], event[3]
                        log_lines = ["Buttons:"]
                        for b_idx, pressed in sorted(buttons_state.items()):
                            if pressed:
                                log_lines.append(f"  [{b_idx}]: PRESSED")
                        log_lines.append("Axes:")
                        for a_idx, val in sorted(axes_state.items()):
                            if abs(val) > 0.05:
                                log_lines.append(f"  Axis {a_idx}: {val}")
                        log_lines.append("Hats:")
                        for h_idx, h_val in sorted(hats_state.items()):
                            if h_val != (0, 0):
                                log_lines.append(f"  Hat {h_idx}: {h_val}")

                        self.input_log_text.configure(state="normal")
                        self.input_log_text.delete("1.0", tk.END)
                        self.input_log_text.insert("1.0", "\n".join(log_lines))
                        self.input_log_text.configure(state="disabled")

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
                    self.save_settings_button.configure(state="disabled")

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
                    self.save_settings_button.configure(state="normal")

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
                    self.save_settings_button.configure(state="normal")
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

    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass

    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
