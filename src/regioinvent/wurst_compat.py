import wurst

try:
    # Wurst >=0.5 can expose top-level extract_brightway2_databases as None when
    # optional Brightway IO imports fail, while the extractor itself is available.
    from wurst.brightway.extract_database import (
        extract_brightway2_databases as wurst_extract_brightway2_databases,
    )
except Exception:
    wurst_extract_brightway2_databases = None


def extract_brightway2_databases_compat(database_name, add_identifiers=True):
    """
    Return a wurst extraction of a Brightway database with compatibility fallback.
    """

    extractor = getattr(wurst, "extract_brightway2_databases", None)
    if not callable(extractor):
        extractor = wurst_extract_brightway2_databases
    if not callable(extractor):
        raise ImportError(
            "wurst.extract_brightway2_databases is unavailable. "
            "Check Brightway and wurst compatibility in the active environment."
        )
    return extractor(database_name, add_identifiers=add_identifiers)
