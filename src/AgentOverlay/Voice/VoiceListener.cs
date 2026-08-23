namespace AgentOverlay.Voice;

/// <summary>
/// Placeholder for speech-to-text. Not wired to the microphone or to any recognition
/// engine yet -- the real choice (offline Whisper vs. a cloud STT API) depends on
/// latency/accuracy/privacy tradeoffs the user hasn't made yet. This just defines the
/// shape the rest of the app expects so that decision can be dropped in later without
/// touching callers.
/// </summary>
public interface IVoiceListener
{
    event Action<string>? PhraseRecognized;

    void Start();
    void Stop();
}

/// <summary>No-op implementation used until a real engine is wired in.</summary>
public sealed class NullVoiceListener : IVoiceListener
{
    public event Action<string>? PhraseRecognized;

    public void Start() { }
    public void Stop() { }
}
