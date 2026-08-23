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
- A small always-visible status badge (top-right) shows which mode is active,
  so the overlay's state is never invisible to you.

### What's stubbed but not wired up

These exist as clean, isolated modules so the architecture is in place, but
none of them are connected to anything yet -- no automatic decision-making or
input injection happens just because the app is running:

- `Input/InputInjector.cs` -- synthesizes mouse moves/clicks and keyboard text
  via `SendInput`. The agent's "hands." Callable manually, not auto-invoked.
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

### Building and running

WPF is Windows-only. Requires the .NET 8 SDK on Windows:

```
cd src/AgentOverlay
dotnet run
```

There is no Linux/macOS build target -- this project is intentionally
Windows-specific (layered windows, `SendInput`, global hotkeys are all Win32).
