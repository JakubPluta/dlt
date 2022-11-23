from typing import Final
from dlt.common.configuration import configspec

from dlt.destinations.postgres.configuration import PostgresClientConfiguration


@configspec(init=True)
class RedshiftClientConfiguration(PostgresClientConfiguration):
    destination_name: Final[str] = "redshift"  # type: ignore
