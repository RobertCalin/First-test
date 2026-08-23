using System.ComponentModel;
using System.Diagnostics;
using System.Text.Json;

namespace AgentOverlay.Gesture;

/// <summary>
/// Runs hand_tracker.py as a child process and turns its stdout (one JSON object per line)
/// into <see cref="HandFrame"/> events. Hand landmark detection is delegated to Google's
/// MediaPipe Python package rather than reimplemented here -- it ships its own pretrained
/// model, so there's no separate model file to source, just `pip install -r requirements.txt`.
/// </summary>
public sealed class PythonHandTracker : IHandTracker
{
    // Adjust if your Python install only registers a different launcher (e.g. "py").
    private const string PythonExecutable = "python";

    public event Action<HandFrame>? FrameReceived;
    public event Action<string>? Failed;

    private Process? _process;
    private CancellationTokenSource? _cts;

    public void Start()
    {
        if (_process is not null)
        {
            return;
        }

        var scriptPath = Path.Combine(AppContext.BaseDirectory, "Gesture", "hand_tracker.py");
        if (!File.Exists(scriptPath))
        {
            Failed?.Invoke($"hand_tracker.py not found at {scriptPath}");
            return;
        }

        var startInfo = new ProcessStartInfo
        {
            FileName = PythonExecutable,
            ArgumentList = { scriptPath },
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
        };

        try
        {
            _process = Process.Start(startInfo);
        }
        catch (Win32Exception ex)
        {
            Failed?.Invoke($"Could not launch '{PythonExecutable}': {ex.Message}. Is Python installed and on PATH?");
            return;
        }

        if (_process is null)
        {
            Failed?.Invoke("Could not launch the hand tracker process.");
            return;
        }

        _cts = new CancellationTokenSource();
        _ = ReadStdoutAsync(_process, _cts.Token);
        _ = DrainStderrAsync(_process, _cts.Token);
    }

    public void Stop()
    {
        _cts?.Cancel();
        _cts?.Dispose();
        _cts = null;

        if (_process is { HasExited: false })
        {
            try
            {
                _process.Kill(entireProcessTree: true);
            }
            catch (InvalidOperationException)
            {
                // Exited between the check above and the kill; nothing left to do.
            }
        }
        _process?.Dispose();
        _process = null;
    }

    private async Task ReadStdoutAsync(Process process, CancellationToken token)
    {
        try
        {
            while (!token.IsCancellationRequested)
            {
                var line = await process.StandardOutput.ReadLineAsync(token);
                if (line is null)
                {
                    if (!token.IsCancellationRequested)
                    {
                        Failed?.Invoke("hand_tracker.py exited unexpectedly.");
                    }
                    return;
                }

                if (string.IsNullOrWhiteSpace(line))
                {
                    continue;
                }

                var frame = TryParseFrame(line);
                if (frame is not null)
                {
                    FrameReceived?.Invoke(frame);
                }
            }
        }
        catch (OperationCanceledException)
        {
            // Expected shutdown path (Stop() cancels before killing the process).
        }
        catch (Exception ex)
        {
            Failed?.Invoke($"hand_tracker.py stdout reader crashed: {ex.Message}");
        }
    }

    private async Task DrainStderrAsync(Process process, CancellationToken token)
    {
        try
        {
            while (!token.IsCancellationRequested)
            {
                var line = await process.StandardError.ReadLineAsync(token);
                if (line is null)
                {
                    return;
                }
                if (!string.IsNullOrWhiteSpace(line))
                {
                    Failed?.Invoke($"hand_tracker.py: {line}");
                }
            }
        }
        catch (OperationCanceledException)
        {
        }
    }

    private static HandFrame? TryParseFrame(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;

            if (root.TryGetProperty("error", out _))
            {
                return null;
            }

            var present = root.GetProperty("hand_present").GetBoolean();
            var gestureText = root.GetProperty("gesture").GetString() ?? "none";
            var x = root.GetProperty("cursor_x").GetDouble();
            var y = root.GetProperty("cursor_y").GetDouble();

            var gesture = gestureText switch
            {
                "pinch" => HandGesture.Pinch,
                "point" => HandGesture.Point,
                "fist" => HandGesture.Fist,
                "open_palm" => HandGesture.OpenPalm,
                _ => HandGesture.None,
            };

            return new HandFrame(present, gesture, x, y);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    public void Dispose() => Stop();
}
