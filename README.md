# First-test

## AgentOverlay

A fullscreen, transparent Windows overlay that is the visual foundation for a
desktop productivity/accessibility agent: something that sits on top of every
other app, can be drawn on, and can (eventually) see the screen, listen for
voice commands, and act across other applications.

Source: [`src/AgentOverlay`](src/AgentOverlay).

### What's implemented (Phase 1)

- A fullscreen, transparent, always-on-top window covering the whole virtual
  desktop (all monitors), hidden from the taskbar/alt-tab.
- Click-through by default: with no input, the overlay is fully invisible to
  clicks and they land on whatever app is beneath it.
- **Ctrl+Alt+D** toggles **Draw Mode**, where the overlay captures mouse input
  and you can ink-draw directly on top of everything on screen. Pressing it
  again returns to click-through.
- **Ctrl+Alt+Q** is a hard kill switch: quits the app instantly, in any mode,
  with no confirmation dialog to fight through.
- A small always-visible status badge (top-right of your **primary monitor**)
  shows which mode is active, so the overlay's state is never invisible to
  you.
- An avatar face centered on your **primary monitor** (Settings > Display >
  the one marked "1"), with eyes that track the live mouse cursor across all
  monitors (polled via `GetCursorPos`, since click-through mode receives no
  mouse events) -- a visible cue that the overlay is "watching." Opaque,
  high-contrast fill with a drop shadow so it reads against any wallpaper.
  Its outline color mirrors the status badge (gray = pass-through, green =
  draw mode). Never hit-test visible, so it can't block clicks or drawing.
  Both indicators are anchored inside a `PrimaryMonitorRegion` sub-grid that
  code-behind sizes/offsets to the primary monitor specifically, since the
  outer window spans the whole multi-monitor virtual desktop.
- A global unhandled-exception handler (`App.xaml.cs`) shows an error dialog
  instead of failing silently, and hotkey registration failures (e.g.
  Ctrl+Alt+D already bound by another app) degrade to a status message
  instead of crashing the app on startup.
- **Hand-gesture mouse control**, armed/disarmed with **Ctrl+Alt+H** (off by
  default -- a webcam pointed at you should never move your mouse without
  explicit opt-in). While armed:
  - Your index fingertip's position drives the cursor.
  - Pinching (thumb + index finger together) performs a click.
  - `Fist` and `open_palm` are detected and available in the event data but
    not yet bound to an action.
  - Hand tracking is delegated to
    [`Gesture/hand_tracker.py`](src/AgentOverlay/Gesture/hand_tracker.py), a
    small Python script using Google's MediaPipe Hands (which ships its own
    pretrained model -- no separate model file to source). `PythonHandTracker`
    launches it as a subprocess only while hand control is armed, and stops
    it (releasing the webcam) the moment you disarm or quit. See **Running
    hand-gesture control** below for the extra setup this needs.

### What's stubbed but not wired up

These exist as clean, isolated modules so the architecture is in place, but
none of them are connected to anything automatically:

- `Input/InputInjector.cs` -- synthesizes mouse moves/clicks and keyboard
  text via `SendInput`. The agent's "hands." Now used by hand-gesture control
  above; still not auto-invoked by anything else.
- `Voice/VoiceListener.cs` -- interface for speech-to-text; the choice between
  an offline engine (e.g. Whisper) and a cloud STT API is deferred.
- `Agent/IAgentBrain.cs` -- the decision loop interface (screenshot + voice
  transcript in, one `AgentAction` out). This is where a call to an LLM (e.g.
  Claude, with vision) will eventually live. Actions are data, not side
  effects, so each one can be logged and, for anything destructive, confirmed
  before `InputInjector` executes it.

### Next steps (roadmap, not yet built)

1. Screen capture (Desktop Duplication API) feeding `AgentContext`.
2. A real `IVoiceListener` implementation + a push-to-talk or wake-word hotkey.
3. A real `IAgentBrain` calling an LLM to turn (screenshot, voice command)
   into an `AgentAction`.
4. A confirmation/logging layer between the brain's decisions and
   `InputInjector` actually executing them, especially for anything
   destructive (submitting forms, deleting, sending messages).
5. Bind `fist`/`open_palm` gestures to additional actions (e.g. drag, or
   toggling pass-through), and smooth/debounce the cursor position -- it
   currently follows the raw fingertip position 1:1, which will feel jittery.

### Building and running

WPF is Windows-only. Requires the .NET 8 SDK on Windows:

```
cd src/AgentOverlay
dotnet run
```

There is no Linux/macOS build target -- this project is intentionally
Windows-specific (layered windows, `SendInput`, global hotkeys are all Win32).

### Running hand-gesture control

Hand tracking needs Python in addition to .NET, since it shells out to
`Gesture/hand_tracker.py`:

1. Install Python 3.9-3.12 from https://python.org (MediaPipe doesn't yet
   support the very latest Python release -- check MediaPipe's PyPI page if
   `pip install` fails on a brand-new Python version). Make sure "Add
   python.exe to PATH" is checked during install.
2. Install the two packages it needs:
   ```
   pip install -r src/AgentOverlay/Gesture/requirements.txt
   ```
3. Run the app as usual (`dotnet run`) and press **Ctrl+Alt+H**. The status
   badge will say "Hand Control ON" once the webcam feed is flowing; if
   Python or a package is missing, it'll show the specific error instead
   (e.g. "Could not launch 'python' ... Is Python installed and on PATH?").

You can also run `python src/AgentOverlay/Gesture/hand_tracker.py` directly
to sanity-check the tracker on its own -- it prints one JSON line per frame
to the terminal (Ctrl+C to stop).
