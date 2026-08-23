namespace AgentOverlay.Gesture;

/// <summary>
/// The agent's "eyes on your hands": watches the webcam and reports one <see cref="HandFrame"/>
/// per camera frame while running. Deliberately does not touch Input.InputInjector itself --
/// the caller decides whether and how frames turn into actual mouse control.
/// </summary>
public interface IHandTracker : IDisposable
{
    event Action<HandFrame>? FrameReceived;

    /// <summary>Raised when tracking can't run or stops unexpectedly, with a human-readable reason.</summary>
    event Action<string>? Failed;

    void Start();
    void Stop();
}
