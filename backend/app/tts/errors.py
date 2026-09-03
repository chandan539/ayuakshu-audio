"""TTS-related errors."""


class ModelNotInstalledError(RuntimeError):
    """Raised when generation is requested but local model weights are missing."""

    def __init__(self, engine: str, hint: str | None = None):
        message = (
            f"TTS model is not installed for engine '{engine}'. "
            "Open Settings → AI Models to install it."
        )
        if hint:
            message = f"{message} ({hint})"
        super().__init__(message)
        self.engine = engine
