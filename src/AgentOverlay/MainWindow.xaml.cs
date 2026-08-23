using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Threading;
using AgentOverlay.Gesture;
using AgentOverlay.Input;
using AgentOverlay.Native;

namespace AgentOverlay;

public partial class MainWindow : Window
{
    // Virtual-key codes for the hotkey combos below (see WinUser.h VK_* constants).
    private const uint VK_D = 0x44;
    private const uint VK_Q = 0x51;
    private const uint VK_H = 0x48;

    private const int HOTKEY_TOGGLE_DRAW = 1;
    private const int HOTKEY_KILL_SWITCH = 2;
    private const int HOTKEY_TOGGLE_HANDS = 3;

    // How far the pupil can move from the eye's center, in device-independent pixels.
    private const double PupilRange = 8.0;

    private GlobalHotkey? _toggleHotkey;
    private GlobalHotkey? _killHotkey;
    private GlobalHotkey? _handsHotkey;
    private DispatcherTimer? _eyeTracker;
    private readonly IHandTracker _handTracker = new PythonHandTracker();
    private bool _drawMode;
    private bool _handControlEnabled;
    private bool _wasPinching;

    public MainWindow()
    {
        InitializeComponent();
        SourceInitialized += OnSourceInitialized;
        Closed += (_, _) =>
        {
            _toggleHotkey?.Dispose();
            _killHotkey?.Dispose();
            _handsHotkey?.Dispose();
            _eyeTracker?.Stop();
            _handTracker.Dispose();
        };
    }

    private void OnSourceInitialized(object? sender, EventArgs e)
    {
        CoverVirtualScreen();
        PositionPrimaryMonitorRegion();

        // Layered is required for real transparency; start click-through so the overlay
        // never blocks whatever is underneath until the user explicitly asks to draw.
        var handle = new WindowInteropHelper(this).Handle;
        var style = NativeMethods.GetWindowLong(handle, NativeMethods.GWL_EXSTYLE);
        NativeMethods.SetWindowLong(handle, NativeMethods.GWL_EXSTYLE,
            style | NativeMethods.WS_EX_LAYERED | NativeMethods.WS_EX_TOOLWINDOW);
        SetClickThrough(true);

        // Hotkey registration can fail if another app already owns the exact combo. That
        // must never take the whole overlay down with it -- surface it in the status text
        // instead of throwing past this point and killing the window before it's visible.
        try
        {
            // Ctrl+Alt+D: toggle between pass-through and draw mode.
            _toggleHotkey = new GlobalHotkey(this, HOTKEY_TOGGLE_DRAW,
                NativeMethods.MOD_CONTROL | NativeMethods.MOD_ALT, VK_D);
            _toggleHotkey.Pressed += () => Dispatcher.Invoke(ToggleDrawMode);
        }
        catch (InvalidOperationException)
        {
            StatusText.Text = "Ctrl+Alt+D unavailable (in use by another app)";
        }

        try
        {
            // Ctrl+Alt+Q: hard kill switch. Always available, in every mode, no confirmation
            // dialog to fight through -- an overlay that can eventually inject input needs an
            // instant, unconditional way to shut it down.
            _killHotkey = new GlobalHotkey(this, HOTKEY_KILL_SWITCH,
                NativeMethods.MOD_CONTROL | NativeMethods.MOD_ALT, VK_Q);
            _killHotkey.Pressed += () => Dispatcher.Invoke(() => Application.Current.Shutdown());
        }
        catch (InvalidOperationException)
        {
            StatusText.Text = "Ctrl+Alt+Q unavailable (in use by another app)";
        }

        try
        {
            // Ctrl+Alt+H: arm/disarm hand-gesture mouse control. Off by default -- a
            // webcam pointed at you should never start moving your mouse without an
            // explicit, deliberate opt-in.
            _handsHotkey = new GlobalHotkey(this, HOTKEY_TOGGLE_HANDS,
                NativeMethods.MOD_CONTROL | NativeMethods.MOD_ALT, VK_H);
            _handsHotkey.Pressed += () => Dispatcher.Invoke(ToggleHandControl);
        }
        catch (InvalidOperationException)
        {
            StatusText.Text = "Ctrl+Alt+H unavailable (in use by another app)";
        }

        _handTracker.FrameReceived += frame => Dispatcher.Invoke(() => OnHandFrame(frame));
        _handTracker.Failed += message => Dispatcher.Invoke(() =>
        {
            _handControlEnabled = false;
            _wasPinching = false;
            StatusText.Text = $"Hand tracker: {message}";
            StatusDot.Fill = Brushes.OrangeRed;
            FaceHead.Stroke = Brushes.OrangeRed;
        });

        // Polls the real cursor position instead of using WPF mouse events, since this
        // window receives no mouse messages at all while click-through is active.
        _eyeTracker = new DispatcherTimer(DispatcherPriority.Render)
        {
            Interval = TimeSpan.FromMilliseconds(16),
        };
        _eyeTracker.Tick += (_, _) => UpdateEyeLook();
        _eyeTracker.Start();
    }

    /// <summary>Points both pupils toward the current mouse position.</summary>
    private void UpdateEyeLook()
    {
        if (!NativeMethods.GetCursorPos(out var cursor))
        {
            return;
        }

        // GetCursorPos returns physical pixels; the window's own Left/Top/size are in
        // device-independent pixels, so convert using this window's DPI scale factor.
        // (Approximate on mixed-DPI multi-monitor setups -- acceptable for a visual cue.)
        var dpi = VisualTreeHelper.GetDpi(this);
        var mouseInWindow = new Point(
            cursor.X / dpi.DpiScaleX - Left,
            cursor.Y / dpi.DpiScaleY - Top);

        var faceCenter = FaceContainer.TranslatePoint(
            new Point(FaceContainer.ActualWidth / 2, FaceContainer.ActualHeight / 2), this);

        var angle = Math.Atan2(mouseInWindow.Y - faceCenter.Y, mouseInWindow.X - faceCenter.X);
        var offsetX = Math.Cos(angle) * PupilRange;
        var offsetY = Math.Sin(angle) * PupilRange;

        LeftPupilTransform.X = offsetX;
        LeftPupilTransform.Y = offsetY;
        RightPupilTransform.X = offsetX;
        RightPupilTransform.Y = offsetY;
    }

    /// <summary>
    /// Sizes the window to cover every monitor in the virtual desktop, not just the
    /// primary one. DPI-aware because of app.manifest's PerMonitorV2 declaration.
    /// </summary>
    private void CoverVirtualScreen()
    {
        Left = SystemParameters.VirtualScreenLeft;
        Top = SystemParameters.VirtualScreenTop;
        Width = SystemParameters.VirtualScreenWidth;
        Height = SystemParameters.VirtualScreenHeight;
    }

    /// <summary>
    /// Sizes and offsets <c>PrimaryMonitorRegion</c> to exactly cover the primary monitor
    /// (Settings &gt; Display &gt; "1"), not the virtual desktop's full bounding box -- on a
    /// multi-monitor setup those only coincide with a symmetric arrangement, and everything
    /// anchored to the outer Grid could otherwise land on a different physical screen than
    /// the one you're looking at. The primary monitor's top-left is always desktop-absolute
    /// (0,0), so this window's own Left/Top (the virtual desktop's top-left, possibly
    /// negative) gives the offset into this window's local coordinates.
    /// </summary>
    private void PositionPrimaryMonitorRegion()
    {
        PrimaryMonitorRegion.Width = SystemParameters.PrimaryScreenWidth;
        PrimaryMonitorRegion.Height = SystemParameters.PrimaryScreenHeight;
        PrimaryMonitorRegion.Margin = new Thickness(-Left, -Top, 0, 0);
    }

    private void ToggleDrawMode() => SetClickThrough(clickThrough: _drawMode);

    private void SetClickThrough(bool clickThrough)
    {
        _drawMode = !clickThrough;

        var handle = new WindowInteropHelper(this).Handle;
        var style = NativeMethods.GetWindowLong(handle, NativeMethods.GWL_EXSTYLE);
        style = clickThrough
            ? style | NativeMethods.WS_EX_TRANSPARENT
            : style & ~NativeMethods.WS_EX_TRANSPARENT;
        NativeMethods.SetWindowLong(handle, NativeMethods.GWL_EXSTYLE, style);

        DrawSurface.IsHitTestVisible = _drawMode;
        UpdateModeVisuals();
    }

    /// <summary>
    /// Arms or disarms live hand-gesture mouse control: while armed, the index fingertip's
    /// position drives the cursor and a pinch performs a click (see OnHandFrame). Starts/stops
    /// the Python hand_tracker.py process alongside the toggle, so the webcam is only ever in
    /// use while this is explicitly on.
    /// </summary>
    private void ToggleHandControl()
    {
        _handControlEnabled = !_handControlEnabled;

        if (_handControlEnabled)
        {
            _handTracker.Start();
            // _handTracker.Failed can fire synchronously from within Start() (e.g. Python
            // isn't on PATH) and flips _handControlEnabled back off with its own status
            // message -- only overwrite that with the generic "on" visuals if it didn't.
            if (_handControlEnabled)
            {
                UpdateModeVisuals();
            }
        }
        else
        {
            _handTracker.Stop();
            _wasPinching = false;
            UpdateModeVisuals();
        }
    }

    /// <summary>
    /// Turns one hand-tracking frame into cursor movement and, on a pinch, a click. This is
    /// the only place gestures reach Input.InputInjector -- nothing here runs unless hand
    /// control was explicitly armed via Ctrl+Alt+H.
    /// </summary>
    private void OnHandFrame(HandFrame frame)
    {
        if (!_handControlEnabled)
        {
            return;
        }

        if (!frame.HandPresent)
        {
            _wasPinching = false;
            return;
        }

        // Mirror X: moving your hand to your right, as you face the camera, should move
        // the cursor right on screen -- matching a mirror/selfie view, not the raw frame.
        var mirroredX = 1.0 - frame.CursorX;

        var screenWidth = SystemParameters.PrimaryScreenWidth;
        var screenHeight = SystemParameters.PrimaryScreenHeight;
        var x = (int)Math.Clamp(mirroredX * screenWidth, 0, screenWidth - 1);
        var y = (int)Math.Clamp(frame.CursorY * screenHeight, 0, screenHeight - 1);

        InputInjector.MoveTo(x, y);

        var isPinching = frame.Gesture == HandGesture.Pinch;
        if (isPinching && !_wasPinching)
        {
            InputInjector.ClickAt(x, y);
        }
        _wasPinching = isPinching;
    }

    /// <summary>Single source of truth for the status badge and face outline color/text.</summary>
    private void UpdateModeVisuals()
    {
        if (_handControlEnabled)
        {
            StatusText.Text = "Hand Control ON (Ctrl+Alt+H to stop)";
            StatusDot.Fill = Brushes.Cyan;
            FaceHead.Stroke = Brushes.Cyan;
        }
        else if (_drawMode)
        {
            StatusText.Text = "Draw Mode (Ctrl+Alt+D to release)";
            StatusDot.Fill = Brushes.LimeGreen;
            FaceHead.Stroke = Brushes.LimeGreen;
        }
        else
        {
            StatusText.Text = "Pass-through";
            StatusDot.Fill = Brushes.Gray;
            FaceHead.Stroke = Brushes.Gray;
        }
    }
}
