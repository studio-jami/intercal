"""Provider-agnostic port interfaces for every external dependency.

Each port is a Protocol (structural typing) or ABC so concrete adapters can be
swapped by configuration without touching domain code.

Import the port you need:
    from intercal_shared.ports.storage import StoragePort
    from intercal_shared.ports.embeddings import EmbeddingsPort
    from intercal_shared.ports.llm import LlmPort
    from intercal_shared.ports.queue import QueuePort
    from intercal_shared.ports.scheduler import SchedulerPort
"""
