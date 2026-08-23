using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using AgentOverlay.Native;

namespace AgentOverlay;

public partial class MainWindow : Window
{
    // Virtual-key codes for the hotkey combos below (see WinUser.h VK_* constants).
    private const uint VK_D = 0x44;
    private const uint VK_Q = 0x51;

    private const int HOTKEY_TOGGLE_DRAW = 1;
    private const int HOTKEY_KILL_SWITCH = 2;

    private GlobalHotkey? _toggleHotkey;
    private GlobalHotkey? _killHotkey;
    private bool _drawMode;

    public MainWindow()
    {
        InitializeComponent();
        SourceInitialized += OnSourceInitialized;
        Closed += (_, _) =>
        {
            _toggleHotkey?.Dispose();
            _killHotkey?.Dispose();
        };
    }

    private void OnSourceInitialized(object? sender, EventArgs e)
    {
        CoverVirtualScreen();

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
    }
}
