using System.Windows;
using System.Windows.Interop;

namespace AgentOverlay.Native;

/// <summary>
/// Registers a single system-wide hotkey and raises <see cref="Pressed"/> when it fires,
/// regardless of which application currently has focus. Must be created after the owning
/// window's handle exists (e.g. in the Window's Loaded/SourceInitialized handler).
/// </summary>
internal sealed class GlobalHotkey : IDisposable
{
    private readonly int _id;
    private readonly HwndSource _source;
    private bool _registered;

    public event Action? Pressed;

    public GlobalHotkey(Window window, int id, uint modifiers, uint virtualKey)
    {
        _id = id;
        var handle = new WindowInteropHelper(window).Handle;
        _source = HwndSource.FromHwnd(handle)
            ?? throw new InvalidOperationException("Window handle is not initialized yet.");

        _source.AddHook(WndProc);
        _registered = NativeMethods.RegisterHotKey(handle, _id, modifiers | NativeMethods.MOD_NOREPEAT, virtualKey);
        if (!_registered)
        {
            // Most common cause: another application already owns this exact combo.
            throw new InvalidOperationException(
                $"Failed to register global hotkey id={_id}. It may already be in use by another app.");
        }
    }

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (msg == NativeMethods.WM_HOTKEY && wParam.ToInt32() == _id)
        {
            Pressed?.Invoke();
            handled = true;
        }
        return IntPtr.Zero;
    }

    public void Dispose()
    {
        if (_registered)
        {
            NativeMethods.UnregisterHotKey(_source.Handle, _id);
            _registered = false;
        }
        _source.RemoveHook(WndProc);
    }
}
