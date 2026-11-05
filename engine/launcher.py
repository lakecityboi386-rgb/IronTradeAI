"""Entry point for the packaged Python sidecar."""

import runpy

if __name__ == "__main__":
    runpy.run_module("engine.server", run_name="__main__")
