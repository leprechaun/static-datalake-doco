from typing import Protocol

from datalake_doco.models import TableDoc


class Reader(Protocol):
    def can_read(self, uri: str, storage_options: dict | None = None) -> bool: ...
    def read(self, uri: str, name: str, sample_count: int = 0, storage_options: dict | None = None) -> TableDoc: ...


from datalake_doco.readers.delta import DeltaReader

READERS: list[Reader] = [DeltaReader()]


def get_reader(uri: str, storage_options: dict | None = None) -> Reader | None:
    for reader in READERS:
        if reader.can_read(uri, storage_options=storage_options):
            return reader
    return None
