using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Threading;
using AgentOverlay.Native;

namespace AgentOverlay;

public partial class MainWindow : Window
{
    // Virtual-key codes for the hotkey combos below (see WinUser.h VK_* constants).
    private const uint VK_D = 0x44;
    private const uint VK_Q = 0x51;

    private const int HOTKEY_TOGGLE_DRAW = 1;
    private const int HOTKEY_KILL_SWITCH = 2;

    // How far the pupil can move from the eye's center, in device-independent pixels.
    private const double PupilRange = 8.0;

    private GlobalHotkey? _toggleHotkey;
    private GlobalHotkey? _killHotkey;
    private DispatcherTimer? _eyeTracker;
    private bool _drawMode;

    public MainWindow()
    {
        InitializeComponent();
        SourceInitialized += OnSourceInitialized;
        Closed += (_, _) =>
        {
            _toggleHotkey?.Dispose();
            _killHotkey?.Dispose();
            _eyeTracker?.Stop();
        };
    }

    private void OnSourceInitialized(object? sender, EventArgs e)
    {
        CoverVirtualScreen();
        PositionFaceOnPrimaryMonitor();

        // Layered is required for real transparency; start click-through so the overlay
        // never blocks whatever is underneath until the user explicitly asks to draw.
        var handle = new WindowInteropHelper(this).Handle;
        var style = NativeMethods.GetWindowLong(handle, NativeMethods.GWL_EXSTYLE);
        NativeMethods.SetWindowLong(handle, NativeMethods.GWL_EXSTYLE,
            style | NativeMethods.WS_EX_LAYERED | NativeMethods.WS_EX_TOOLWINDOW);
        SetClickThrough(true);

        // Ctrl+Alt+D: toggle between pass-through and draw mode.
        _toggleHotkey = new GlobalHotkey(this, HOTKEY_TOGGLE_DRAW,
            NativeMethods.MOD_CONTROL | NativeMethods.MOD_ALT, VK_D);
        _toggleHotkey.Pressed += () => Dispatcher.Invoke(ToggleDrawMode);

        // Ctrl+Alt+Q: hard kill switch. Always available, in every mode, no confirmation
        // dialog to fight through -- an overlay that can eventually inject input needs an
        // instant, unconditional way to shut it down.
        _killHotkey = new GlobalHotkey(this, HOTKEY_KILL_SWITCH,
            NativeMethods.MOD_CONTROL | NativeMethods.MOD_ALT, VK_Q);
        _killHotkey.Pressed += () => Dispatcher.Invoke(() => Application.Current.Shutdown());

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
    /// Places the face at the center of the primary monitor (Settings &gt; Display &gt; "1"),
    /// not the center of the virtual desktop's bounding box -- on a multi-monitor setup
    /// those only coincide with a symmetric arrangement. The primary monitor's top-left is
    /// always desktop-absolute (0,0), so this window's own Left/Top (the virtual desktop's
    /// top-left, possibly negative) gives the offset into this window's local coordinates.
    /// </summary>
    private void PositionFaceOnPrimaryMonitor()
    {
        var primaryCenterX = SystemParameters.PrimaryScreenWidth / 2 - Left;
        var primaryCenterY = SystemParameters.PrimaryScreenHeight / 2 - Top;

        FaceContainer.Margin = new Thickness(
            primaryCenterX - FaceContainer.Width / 2,
            primaryCenterY - FaceContainer.Height / 2,
            0, 0);
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
        StatusText.Text = _drawMode ? "Draw Mode (Ctrl+Alt+D to release)" : "Pass-through";
        StatusDot.Fill = _drawMode ? Brushes.LimeGreen : Brushes.Gray;
        FaceHead.Stroke = _drawMode ? Brushes.LimeGreen : Brushes.Gray;
    }
}
