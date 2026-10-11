"""Reciprocal admission for the desktop's connection-bound idle workflows.

This is UI transaction ownership, not a firmware interlock or permission to
bypass the individual workflow's status, context and receipt checks.
"""


def exchange_pending(workspace):
    panel = getattr(workspace, "tool_exchange_panel", None)
    binding = getattr(workspace.control_owner, "binding", None)
    return bool(
        panel is not None
        and binding is not None
        and panel.operation_binding == (binding.session_id, binding.connection_id)
    )


def require_idle_transaction(workspace, requester):
    if requester != "exchange" and exchange_pending(workspace):
        raise ValueError("The selected connection has a pending or unresolved tool exchange; inspect its receipt first")
    job = getattr(workspace, "job_file_panel", None)
    if requester != "job" and job is not None and (job.busy or job.run_panel.active or job.run_panel.journaling):
        raise ValueError("The machine-file or run workflow owns an unfinished transaction")
    probe = getattr(workspace, "probe_settings_panel", None)
    if requester != "probe" and probe is not None and probe.busy:
        raise ValueError("The probe-settings workflow owns an unfinished transaction")
