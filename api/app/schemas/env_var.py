"""EnvVar schema: represents a single environment variable with optional sensitive flag.

Non-sensitive vars are stored in GitOps values.yaml as plaintext.
Sensitive vars are written to a K8s Secret and referenced via envFrom.
"""

from pydantic import BaseModel, Field


class EnvVar(BaseModel):
    """A single environment variable, optionally marked as sensitive."""

    key: str = Field(
        ...,
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        description="Environment variable name (must match shell identifier rules)",
    )
    value: str = Field(
        ...,
        max_length=32768,
        description="Environment variable value (max 32 KiB)",
    )
    sensitive: bool = Field(
        default=False,
        description="If true, value is stored in a K8s Secret instead of values.yaml",
    )


class EnvVarList(BaseModel):
    """A list of environment variables for bulk operations."""

    vars: list[EnvVar] = Field(default_factory=list)

    def plaintext(self) -> dict[str, str]:
        """Return only non-sensitive vars as a plain dict."""
        return {v.key: v.value for v in self.vars if not v.sensitive}

    def sensitive(self) -> dict[str, str]:
        """Return only sensitive vars as a plain dict."""
        return {v.key: v.value for v in self.vars if v.sensitive}
