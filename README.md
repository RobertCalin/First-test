# First-test

## AgentOverlay

A fullscreen, transparent Windows overlay that is the visual foundation for a
desktop productivity/accessibility agent: something that sits on top of every
other app, can be drawn on, controlled by hand gestures via webcam, and can
(eventually) see the screen, listen for voice commands, and act across other
applications.

Source: [`src/agent_overlay`](src/agent_overlay). Pure Python (PySide6/Qt +
ctypes for Win32 interop) -- an earlier C#/WPF version of this same app was
replaced with this one so the whole project (including the ML-heavy
hand-tracking piece) lives in one runtime/language instead of two.

### What's implemented (Phase 1)

- A fullscreen, transparent, always-on-top window covering the whole virtual
  desktop (all monitors), hidden from the taskbar/alt-tab.
- Click-through by default: with no input, the overlay is fully invisible to
  clicks and they land on whatever app is beneath it.
- **Ctrl+Alt+D** toggles **Draw Mode**, where the overlay captures mouse input
  and you can freehand-draw directly on top of everything on screen. Pressing
  it again returns to click-through.
- **Ctrl+Alt+Q** is a hard kill switch: quits the app instantly, in any mode,
  with no confirmation dialog to fight through.
- A small always-visible status badge (top-right of your **primary monitor**)
  shows which mode is active, so the overlay's state is never invisible to
  you.
- An avatar face centered on your **primary monitor** (Settings > Display >
  the one marked "1"), with eyes that track the live mouse cursor across all
  monitors -- a visible cue that the overlay is "watching." Its outline color
  mirrors the status badge (gray = pass-through, green = draw mode, cyan =
  hand control). Never intercepts clicks or drawing.
- A global exception hook (`main.py`) shows an error dialog instead of failing
  silently, and hotkey registration failures (e.g. Ctrl+Alt+D already bound by
  another app) degrade to a status message instead of crashing on startup.
- **Hand-gesture mouse control**, armed/disarmed with **Ctrl+Alt+H** (off by
  default -- a webcam pointed at you should never move your mouse without
  explicit opt-in). Arming it starts with a **4-second calibration**: move
  your hand around your comfortable range of motion (the status badge counts
  it down) so that range -- not the camera's full field of view -- gets
  mapped to the whole screen. Re-arming (toggle off, then on) re-calibrates
  from scratch. Once calibration finishes:
  - Your index fingertip's position drives the cursor.
  - Pinching (thumb + index finger together) performs a click.
  - Two small badges stacked below the status badge show live feedback:
    **Movement** (`Up`/`Down`/`Left`/`Right`/`Still`, classified from
    frame-to-frame fingertip position) and **Action** (the current gesture:
    `Point`/`Pinch`/`Fist`/`Open`/`None`).
  - `fist` and `open_palm` are detected and shown in the Action label but
    not yet bound to a control action.
  - Hand tracking (`hand_tracker.py`) runs on a background thread using
    Google's MediaPipe Tasks HandLandmarker. Unlike the old C# version, this
    now runs in-process rather than as a subprocess talking over stdout. The
    model file (~10MB) isn't bundled in the pip package -- it's downloaded
    automatically to `src/agent_overlay/models/` the first time you arm hand
    control, and cached there after that.

### What's stubbed but not wired up

- `input_injector.py` -- synthesizes mouse moves/clicks and keyboard text via
  `SendInput`. The agent's "hands." Used by hand-gesture control above; still
  not auto-invoked by anything else.
- `voice_listener.py` -- interface for speech-to-text; the choice between an
  offline engine (e.g. Whisper) and a cloud STT API is deferred.
- `agent_brain.py` -- the decision loop interface (screenshot + voice
  transcript in, one `AgentAction` out). This is where a call to an LLM (e.g.
  Claude, with vision) will eventually live. Actions are data, not side
  effects, so each one can be logged and, for anything destructive, confirmed
  before `input_injector` executes it.

### Next steps (roadmap, not yet built)

1. Screen capture feeding `AgentContext`.
2. A real `VoiceListener` implementation + a push-to-talk or wake-word hotkey.
3. A real `AgentBrain` calling an LLM to turn (screenshot, voice command) into
   an `AgentAction`.
4. A confirmation/logging layer between the brain's decisions and
   `input_injector` actually executing them, especially for anything
   destructive (submitting forms, deleting, sending messages).
5. Bind `fist`/`open_palm` gestures to additional actions (e.g. drag, or
   toggling pass-through), and smooth/debounce the cursor position -- it
   currently follows the raw fingertip position 1:1, which will feel jittery.

### Building and running

Windows only (layered windows, `SendInput`, and global hotkeys are all Win32
APIs reached via `ctypes`). Requires Python 3.10+ on Windows.

**First time:**
```
git clone https://github.com/RobertCalin/First-test.git
cd First-test
```

**Every time after that**, just double-click [`run.bat`](run.bat) (or run
`run.bat` from a terminal in the repo root). It pulls the latest code,
creates/updates the virtual environment and dependencies if needed, and
launches the app -- safe to re-run any time, each step is a no-op if there's
nothing new.

(To do the same thing manually instead:
`git pull` -> `python -m venv .venv` -> `.venv\Scripts\activate` ->
`pip install -r requirements.txt` -> `cd src` -> `python -m agent_overlay`.)

MediaPipe doesn't always support the very latest Python release the day it
ships -- if `pip install` fails on `mediapipe`, check
https://pypi.org/project/mediapipe/ for its currently supported Python
versions, or use Python 3.11/3.12.

Controls once it's running:
- `Ctrl+Alt+D` -- toggle Draw Mode
- `Ctrl+Alt+H` -- arm/disarm hand-gesture mouse control (needs a working
  webcam; the status badge will show a specific error if the camera or
  MediaPipe/OpenCV aren't available)
- `Ctrl+Alt+Q` -- quit (also the only clean way to close it, since there's no
  window chrome or taskbar icon)

If it seems stuck with no way to close it: open Task Manager
(`Ctrl+Shift+Esc`) -> find the Python process running `agent_overlay` -> End
Task.
