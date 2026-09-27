"""Explicit backend registry. Unknown backends never fall through."""
class Adapter:
    def __init__(self, backend): self.backend = backend
    def invoke(self, request):
        if self.backend == "codex":
            import codex_dispatch
            return codex_dispatch.run_dispatch(request, request.get("runtime", {}))
        import opencode_dispatch
        return opencode_dispatch.invoke(request)
    def cancel(self, ownership):
        import codex_process
        return codex_process.stop_owned_processes(ownership.get("processes", []), ownership.get("grace_seconds", 1))


def resolve(backend):
    if backend not in ("codex", "opencode"):
        raise ValueError("unsupported backend: %s" % backend)
    return Adapter(backend)
