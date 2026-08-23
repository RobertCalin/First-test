namespace AgentOverlay.Gesture;

public enum HandGesture
{
    None,
    Point,
    Pinch,
    Fist,
    OpenPalm,
}

/// <summary>
/// One frame of hand-tracking output. CursorX/Y are the index fingertip's position in
/// normalized camera-space coordinates (0..1), in the camera's native (unmirrored)
/// left-right orientation -- a caller mapping this to screen coordinates for a
/// front-facing webcam should mirror X so "move your hand right" moves the cursor right.
/// </summary>
public sealed record HandFrame(bool HandPresent, HandGesture Gesture, double CursorX, double CursorY);
