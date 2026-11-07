"""Optional local web workbench; not imported by the core library."""

from .session import GenerationSession
from .workbench import WorkbenchSession

__all__ = ["GenerationSession", "WorkbenchSession"]
