#!/usr/bin/env python3
"""
mixlog.py - beleženje vnosa z miško in tipkovnico s časovnimi žigi.
Deluje po principu RUI (Morgan idr., 2013), za macOS na Apple Silicon.

Namestitev (enkrat):
    pip install pynput
    System Settings -> Privacy & Security -> Input Monitoring  -> dodaj Terminal
    System Settings -> Privacy & Security -> Accessibility     -> dodaj Terminal
    (nato Terminal zapri in ponovno odpri)

Snemanje:
    python3 mixlog.py record --session CBA_stereo_1
    - ustavi s Ctrl+C v oknu Terminala
    - marker (začetek/konec miksa): Ctrl+Option+Cmd+M

Analiza (lahko jo ponoviš z drugim pragom):
    python3 mixlog.py summary logs/CBA_stereo_1.csv --idle 60 --app "Logic Pro"

CSV stolpci:
    t_unix       čas dogodka (Unix, sekunde)
    t_elapsed_s  čas od začetka snemanja (sekunde)
    event        mouse_down | mouse_up | scroll | move | key | marker | start | stop
    detail       gumb miške / tipka z modifikatorji / smer drsenja
    x, y         položaj miške (piksli)
    app          aplikacija v ospredju
Imena tipk se zapišejo samo, ko je v ospredju ciljna aplikacija (--app);
drugje se zapiše samo "<key>".
"""
import argparse
import csv
import os
import sys
import threading
import time
from datetime import datetime

FIELDS = ["t_unix", "t_elapsed_s", "event", "detail", "x", "y", "app"]
MOD_NAMES = {
    "cmd": "cmd", "cmd_l": "cmd", "cmd_r": "cmd",
    "ctrl": "ctrl", "ctrl_l": "ctrl", "ctrl_r": "ctrl",
    "alt": "alt", "alt_l": "alt", "alt_r": "alt",
    "shift": "shift", "shift_l": "shift", "shift_r": "shift",
}


# --------------------------------------------------------------------------
# Snemanje
# --------------------------------------------------------------------------
class Recorder:
    def __init__(self, path, target_app, moves_hz):
        self.path = path
        self.target_app = target_app
        self.move_interval = 1.0 / moves_hz if moves_hz > 0 else None
        self.t0 = time.time()
        self.app = "unknown"
        self.lock = threading.Lock()
        self.last_move = 0.0
        self.mods = set()
        self.pressed = set()
        self.counts = {"mouse_down": 0, "key": 0, "scroll": 0, "marker": 0}
        self.f = open(path, "w", newline="", encoding="utf-8")
        self.w = csv.writer(self.f)
        self.w.writerow(FIELDS)

    def log(self, event, detail="", x="", y=""):
        t = time.time()
        with self.lock:
            self.w.writerow([f"{t:.3f}", f"{t - self.t0:.3f}", event, detail,
                             x if x == "" else int(x), y if y == "" else int(y),
                             self.app])
            self.f.flush()
            if event in self.counts:
                self.counts[event] += 1

    # --- miška ---
    def on_move(self, x, y):
        if self.move_interval is None:
            return
        now = time.monotonic()
        if now - self.last_move >= self.move_interval:
            self.last_move = now
            self.log("move", "", x, y)

    def on_click(self, x, y, button, pressed):
        name = getattr(button, "name", str(button))
        self.log("mouse_down" if pressed else "mouse_up", name, x, y)

    def on_scroll(self, x, y, dx, dy):
        self.log("scroll", f"{dx},{dy}", x, y)

    # --- tipkovnica ---
    @staticmethod
    def key_name(key):
        name = getattr(key, "name", None)
        if name:
            return name
        char = getattr(key, "char", None)
        if char:
            return char.lower()
        vk = getattr(key, "vk", None)
        return f"vk{vk}" if vk is not None else str(key)

    def on_press(self, key):
        name = self.key_name(key)
        if name in self.pressed:          # samodejno ponavljanje ob držanju tipke
            return
        self.pressed.add(name)
        if name in MOD_NAMES:
            self.mods.add(MOD_NAMES[name])
            return
        if self.mods >= {"ctrl", "alt", "cmd"} and name == "m":
            self.log("marker", f"marker_{self.counts['marker'] + 1}")
            print(f"  marker {self.counts['marker']} zapisan")
            return
        combo = "+".join(sorted(self.mods) + [name])
        detail = combo if self.app == self.target_app else "<key>"
        self.log("key", detail)

    def on_release(self, key):
        name = self.key_name(key)
        self.pressed.discard(name)
        if name in MOD_NAMES:
            self.mods.discard(MOD_NAMES[name])


def frontmost_app_getter():
    """Vrne funkcijo, ki prebere ime aplikacije v ospredju (kliče se v glavni niti)."""
    try:
        from AppKit import NSWorkspace
        ws = NSWorkspace.sharedWorkspace()

        def get():
            app = ws.frontmostApplication()
            return str(app.localizedName()) if app else "unknown"
        return get
    except ImportError:
        return lambda: "unknown"


def run_loop_step(seconds):
    """Glavna nit mora poganjati run loop, da macOS posodablja aplikacijo v ospredju."""
    try:
        from Foundation import NSDate, NSRunLoop
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(seconds))
    except ImportError:
        time.sleep(seconds)


def cmd_record(args):
    try:
        from pynput import keyboard, mouse
    except ImportError:
        sys.exit("Manjka knjižnica pynput. Namesti jo z: pip install pynput")

    os.makedirs(args.out, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(args.out, f"{args.session}_{stamp}.csv")
    rec = Recorder(path, args.app, args.moves_hz)
    get_app = frontmost_app_getter()
    rec.app = get_app()
    rec.log("start", args.session)

    ml = mouse.Listener(on_move=rec.on_move, on_click=rec.on_click, on_scroll=rec.on_scroll)
    kl = keyboard.Listener(on_press=rec.on_press, on_release=rec.on_release)
    ml.start()
    kl.start()
    print(f"Snemam v {path}")
    print("Ctrl+C = ustavi, Ctrl+Option+Cmd+M = marker")

    try:
        while True:
            run_loop_step(0.2)
            rec.app = get_app()
    except KeyboardInterrupt:
        pass
    finally:
        rec.log("stop", args.session)
        ml.stop()
        kl.stop()
        rec.f.close()
        print(f"\nShranjeno: {path}\n")
        summarize(path, args.idle, args.app)


# --------------------------------------------------------------------------
# Analiza
# --------------------------------------------------------------------------
def load(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["t"] = float(r["t_unix"])
    return rows


def stats(rows, idle, app, drag_px=5, scroll_gap=0.3):
    if len(rows) < 2:
        return None
    total = rows[-1]["t"] - rows[0]["t"]
    active = 0.0
    in_app = 0.0
    for a, b in zip(rows, rows[1:]):
        gap = b["t"] - a["t"]
        if a["app"] == app:
            in_app += gap
            if gap <= idle:
                active += gap

    clicks = drags = keys = scroll_gestures = 0
    down = None
    last_scroll = None
    for r in rows:
        if r["app"] != app:
            continue
        ev = r["event"]
        if ev == "mouse_down":
            down = r
        elif ev == "mouse_up" and down is not None:
            dist = abs(int(r["x"]) - int(down["x"])) + abs(int(r["y"]) - int(down["y"]))
            if dist > drag_px:
                drags += 1
            else:
                clicks += 1
            down = None
        elif ev == "key":
            keys += 1
        elif ev == "scroll":
            if last_scroll is None or r["t"] - last_scroll > scroll_gap:
                scroll_gestures += 1
            last_scroll = r["t"]
    return {
        "skupni čas [min]": total / 60,
        f"čas v '{app}' [min]": in_app / 60,
        f"aktivni čas (prag {idle:g} s) [min]": active / 60,
        "kliki": clicks,
        "vlečenja (drag)": drags,
        "tipke": keys,
        "drsenja (geste)": scroll_gestures,
    }


def print_stats(title, s):
    print(title)
    if s is None:
        print("  premalo dogodkov")
        return
    for k, v in s.items():
        print(f"  {k:<32} {v:.2f}" if isinstance(v, float) else f"  {k:<32} {v}")


def summarize(path, idle, app):
    rows = load(path)
    print_stats(f"Celotna seja: {os.path.basename(path)}", stats(rows, idle, app))
    marks = [i for i, r in enumerate(rows) if r["event"] == "marker"]
    for n, (i, j) in enumerate(zip(marks, marks[1:]), start=1):
        print_stats(f"\nOdsek med markerjema {n} in {n + 1}:", stats(rows[i:j + 1], idle, app))


def cmd_summary(args):
    summarize(args.file, args.idle, args.app)


def main():
    p = argparse.ArgumentParser(description="Beleženje vnosa po principu RUI.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", help="snemaj dogodke")
    r.add_argument("--session", required=True, help="ime seje, npr. CBA_stereo_1")
    r.add_argument("--out", default="logs", help="mapa za CSV (privzeto: logs)")
    r.add_argument("--app", default="Logic Pro", help="ciljna aplikacija")
    r.add_argument("--moves-hz", type=float, default=10,
                   help="največ zapisov premika miške na sekundo (0 = brez)")
    r.add_argument("--idle", type=float, default=60, help="prag neaktivnosti v s")
    r.set_defaults(func=cmd_record)

    s = sub.add_parser("summary", help="izračunaj mere iz CSV")
    s.add_argument("file")
    s.add_argument("--app", default="Logic Pro")
    s.add_argument("--idle", type=float, default=60)
    s.set_defaults(func=cmd_summary)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
