using System.Windows;
using System.Windows.Threading;

namespace AgentOverlay;

public partial class App : Application
{
    public App()
    {
        // An overlay app that fails silently is worse than useless -- with no console
        // window (WinExe) and nothing else visible, a swallowed startup exception would
        // otherwise look identical to "it's running but invisible."
        DispatcherUnhandledException += (_, e) =>
        {
            MessageBox.Show(
                $"AgentOverlay crashed on startup:\n\n{e.Exception}",
                "AgentOverlay - Unhandled Exception",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
            e.Handled = true;
            Shutdown();
        };
    }
}
