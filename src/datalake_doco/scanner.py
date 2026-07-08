import fsspec


def _strip_trailing_slash(uri: str) -> str:
    return uri.rstrip("/")


def scan(uri: str, endpoint_url: str | None = None) -> list[tuple[str, str]]:
    """Return list of (table_uri, table_name) for all Delta tables under uri."""
    uri = _strip_trailing_slash(uri)
    protocol = uri.split("://")[0] if "://" in uri else "file"
    root_path = uri.split("://", 1)[1] if "://" in uri else uri

    fs_kwargs: dict = {}
    if protocol == "s3" and endpoint_url:
        fs_kwargs["client_kwargs"] = {"endpoint_url": endpoint_url}

    fs = fsspec.filesystem(protocol, **fs_kwargs)

    tables: list[tuple[str, str]] = []
    _walk(fs, protocol, root_path, uri, tables)
    return tables


def _walk(fs, protocol: str, path: str, root_uri: str, tables: list) -> None:
    try:
        entries = fs.ls(path, detail=True)
    except Exception:
        return

    names = {e["name"].rstrip("/").split("/")[-1] for e in entries}

    if "_delta_log" in names:
        table_uri = _build_uri(protocol, path)
        table_name = _derive_name(table_uri, root_uri)
        tables.append((table_uri, table_name))
        return  # don't recurse into a delta table

    for entry in entries:
        if entry.get("type") == "directory" or entry.get("isdir"):
            _walk(fs, protocol, entry["name"], root_uri, tables)


def _build_uri(protocol: str, path: str) -> str:
    if protocol == "file":
        return path
    return f"{protocol}://{path}"


def _derive_name(table_uri: str, root_uri: str) -> str:
    root = root_uri.rstrip("/")
    uri = table_uri.rstrip("/")
    if uri.startswith(root):
        relative = uri[len(root):].lstrip("/")
        return relative or uri.split("/")[-1]
    return uri.split("/")[-1]
