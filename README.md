# mixlog

Timestamped mouse and keyboard logger for macOS (Apple Silicon), modelled on
RUI – Recording User Input (Morgan et al., 2013). RUI 2.1 for Mac is a 32-bit
i386 binary and does not run on current macOS, so this script reimplements the
same idea in Python.

Written for a university project (FRI, University of Ljubljana, course
*3D zvok v multimediji*) that compares the mixing effort of object-based and
channel-based audio production in Logic Pro.

## What it logs

One CSV row per event:

| column | meaning |
|---|---|
| `t_unix` | event time (Unix seconds) |
| `t_elapsed_s` | seconds since recording started |
| `event` | `mouse_down`, `mouse_up`, `scroll`, `move`, `key`, `marker`, `start`, `stop` |
| `detail` | mouse button, key with modifiers (e.g. `cmd+z`), or scroll direction |
| `x`, `y` | mouse position in pixels |
| `app` | application in the foreground |

Key names are written only while the target application (`--app`, default
`Logic Pro`) is in the foreground. In other applications only `<key>` is
written, so passwords and messages are not recorded. Mouse moves are sampled
at most 10 times per second (`--moves-hz`).

## Install

```
pip install pynput
```

System Settings → Privacy & Security → add Terminal to **Input Monitoring**
and **Accessibility**, then restart Terminal.

## Use

```
python3 mixlog.py record --session CBA_stereo_1
```

- `Ctrl+Option+Cmd+M` writes a marker (start / end of a task)
- `Ctrl+C` in Terminal stops recording and prints a summary
- logs are saved to `logs/<session>_<date-time>.csv`

Recompute the summary, e.g. with a different idle threshold:

```
python3 mixlog.py summary logs/<file>.csv --idle 60 --app "Logic Pro"
```

## Summary measures

Computed for the whole session and for each segment between two markers:

- total time
- time with the target app in the foreground
- active time: gaps between events longer than `--idle` seconds are not counted
- clicks (mouse down/up within 5 px), drags (more than 5 px)
- key presses (auto-repeat ignored, modifier keys counted as part of the combination)
- scroll gestures (scroll events less than 0.3 s apart count as one)

## Reference

J. H. Morgan, C.-Y. Cheng, C. Pike, F. E. Ritter, "A Design, Tests and
Considerations for Improving Keystroke and Mouse Loggers", *Interacting with
Computers*, vol. 25, no. 3, 2013. doi:10.1093/iwc/iws014

## License

MIT
