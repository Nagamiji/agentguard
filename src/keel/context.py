import contextvars

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
org_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("org_id", default=None)
run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("run_id", default=None)


def set_request_id(request_id: str | None) -> contextvars.Token[str | None]:
    return request_id_var.set(request_id)


def get_request_id() -> str | None:
    return request_id_var.get()


def set_org_id(org_id: str | None) -> contextvars.Token[str | None]:
    return org_id_var.set(org_id)


def get_org_id() -> str | None:
    return org_id_var.get()


def set_run_id(run_id: str | None) -> contextvars.Token[str | None]:
    return run_id_var.set(run_id)


def get_run_id() -> str | None:
    return run_id_var.get()
