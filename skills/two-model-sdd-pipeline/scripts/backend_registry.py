"""Explicit backend registry with strict request/runtime separation."""


class Adapter:
    def __init__(self, backend, runtime=None):
        self.backend = backend
        self.runtime = runtime

    def invoke(self, request):
        if not isinstance(request, dict) or request.get("backend") != self.backend:
            raise ValueError("request backend does not match selected adapter")
        if self.backend == "codex":
            if not isinstance(self.runtime, dict):
                raise ValueError("Codex runtime envelope must be supplied separately")
            import codex_dispatch
            return codex_dispatch.run_dispatch(request, self.runtime)
        import opencode_dispatch
        return opencode_dispatch.invoke(request)

    def cancel(self, ownership):
        if self.backend == "opencode":
            # This adapter has no verified process ownership/cancellation
            # contract. Never guess at a PID or call the Codex process killer.
            return {"supported": False, "backend": "opencode",
                    "reason": "OpenCode process cancellation is unsupported"}
        if not isinstance(ownership, dict):
            raise ValueError("Codex ownership envelope is required")
        import codex_process
        codex_process.stop_owned_processes(
            ownership.get("processes", []), ownership.get("grace_seconds", 1))
        return {"supported": True, "backend": "codex"}


def resolve(backend, runtime=None):
    if backend not in ("codex", "opencode"):
        raise ValueError("unsupported backend: %s" % backend)
    if backend == "opencode" and runtime is not None:
        raise ValueError("OpenCode runtime must not receive Codex runtime envelope")
    return Adapter(backend, runtime)
