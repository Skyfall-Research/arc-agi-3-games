"""Maintainer tools — never imported by the pipeline.

Nothing under `gen/tools/` is wired into a stage, the orchestrator or a config
reader: these are CLIs a human runs by hand between batches. Keeping them in
their own package is what makes that visible — a stage that needed one would be
a design change, not an import.
"""
