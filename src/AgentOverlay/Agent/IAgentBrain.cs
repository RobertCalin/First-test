namespace AgentOverlay.Agent;

/// <summary>What the brain saw when it made a decision: a screenshot and/or a voice command.</summary>
public sealed record AgentContext(byte[]? ScreenshotPng, string? VoiceCommand);

/// <summary>
/// One atomic action the agent wants to perform. Intentionally data-only: deciding an
/// action and executing it (via Input.InputInjector) are separate steps, so every action
/// can be logged and, for anything destructive, confirmed before it runs.
/// </summary>
public abstract record AgentAction
{
    public sealed record NoOp : AgentAction;
    public sealed record ClickAt(int X, int Y) : AgentAction;
    public sealed record TypeText(string Text) : AgentAction;
    public sealed record Speak(string Text) : AgentAction;
}

/// <summary>
/// The decision loop: given what the agent currently perceives, decide the next action.
/// No implementation is wired in yet -- this is where a call to an LLM (e.g. via the
/// Claude API, using vision + the voice transcript) will eventually live.
/// </summary>
public interface IAgentBrain
{
    Task<AgentAction> DecideNextActionAsync(AgentContext context, CancellationToken cancellationToken);
}

/// <summary>Stub that never acts. Placeholder until a real brain is wired in.</summary>
public sealed class StubAgentBrain : IAgentBrain
{
    public Task<AgentAction> DecideNextActionAsync(AgentContext context, CancellationToken cancellationToken)
        => Task.FromResult<AgentAction>(new AgentAction.NoOp());
}
