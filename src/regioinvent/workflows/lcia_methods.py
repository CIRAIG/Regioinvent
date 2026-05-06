from importlib.resources import as_file, files

import bw2data as bd
import bw2io as bi
import numpy as np


def _has_method_family(method_fragment):
    if 'ReCiPe' in method_fragment:
        return any(method for method in bd.methods if "regionalized" in method[0] and "ReCiPe 2016 v1.03" in method[0])
    elif 'EF' in method_fragment:
        return any(method for method in bd.methods if "regionalized" in method[0] and "EF v3.1" in method[0])
    elif 'IMPACT World+' in method_fragment:
        # TODO don't forget to update version number of IW+ in list comprehension
        return any(method for method in bd.methods if "regionalized" in method[0] and "IMPACT World+" in method[0] and
                   "2.1" in method[0])


def _import_method_package(regio, relpath, method_fragment, label):
    if _has_method_family(method_fragment):
        regio.logger.info(f"Regionalized {label} already present in Brightway project; skipping import.")
        return

    with as_file(files("regioinvent").joinpath(relpath)) as file_path:
        try:
            bi.BW2Package.import_file(file_path)
        except EOFError:
            regio.logger.warning(
                f"Failed importing {label} due to EOFError while backing up existing methods. "
                "This usually means methods already exist with corrupted backup state. "
                "Skipping import."
            )


def import_fully_regionalized_impact_method(regio, lcia_method="all"):
    """
    Function to import a fully regionalized impact method into your brightway project, to-be-used with the
    spatialized version of ecoinvent. You can choose between IMPACT World+, EF and ReCiPe, or simply all of them.

    :param lcia_method: [str] the name of the LCIA method to be imported to be used with the spatialized ecoinvent,
                            available methods are "IW v2.2.1", "EF v3.1", "ReCiPe 2016 v1.03 (H)" or "all".
    :return:
    """

    if lcia_method not in ["IW v2.2.1", "EF v3.1", "ReCiPe 2016 v1.03 (H)", "all"]:
        raise KeyError(
            "Available LCIA methods are: 'IW v2.2.1', 'EF v3.1', 'ReCiPe 2016 v1.03 (H)' or 'all'"
        )

    # Compatibility for older Brightway code paths that still reference np.NaN.
    if not hasattr(np, "NaN"):
        np.NaN = np.nan

    # just load the correct BW2Package file from Data storage folder
    if lcia_method == "all" and regio.ecoinvent_version == "3.12":
        regio.logger.info(
            "Importing all available fully regionalized lcia methods for ecoinvent3.12."
        )

        _import_method_package(
            regio,
            "data/IW/impact_world_plus_221_regionalized-for-ecoinvent-v312.10af03e7ebbf7434cc89b2f3dafde784.bw2package",
            "IMPACT World+ v2.2.1",
            "IMPACT World+ v2.2.1",
        )
        _import_method_package(
            regio,
            "data/EF/EF31_regionalized-for-ecoinvent-v312.06629f91f6a9326caa9145ff3a554e5a.bw2package",
            "EF v3.1",
            "EF v3.1",
        )
        _import_method_package(
            regio,
            "data/ReCiPe/ReCiPe_regionalized-for-ecoinvent-v312.b0a09c06a9dce92251062e2e65ccda54.bw2package",
            "ReCiPe 2016 v1.03 (H)",
            "ReCiPe 2016 v1.03 (H)",
        )

    elif lcia_method == "all" and regio.ecoinvent_version == "3.11":
        regio.logger.info(
            "Importing all available fully regionalized lcia methods for ecoinvent3.11."
        )

        _import_method_package(
            regio,
            "data/IW/impact_world_plus_221_regionalized-for-ecoinvent-v311.6674794954d1b190e85f28b287389bab.bw2package",
            "IMPACT World+ v2.2.1",
            "IMPACT World+ v2.2.1",
        )
        _import_method_package(
            regio,
            "data/EF/EF31_regionalized-for-ecoinvent-v311.bdc82d0c5585c24e5558c33b468d8b7c.bw2package",
            "EF v3.1",
            "EF v3.1",
        )
        _import_method_package(
            regio,
            "data/ReCiPe/ReCiPe_regionalized-for-ecoinvent-v311.65e67dc615f8a7f38dbdf2d32009c9d8.bw2package",
            "ReCiPe 2016 v1.03 (H)",
            "ReCiPe 2016 v1.03 (H)",
        )

    elif lcia_method == "all" and regio.ecoinvent_version == "3.10":
        regio.logger.info(
            "Importing all available fully regionalized lcia methods for ecoinvent3.10."
        )

        _import_method_package(
            regio,
            "data/IW/impact_world_plus_221_regionalized-for-ecoinvent-v310.e9543c08fd29c637c1b24faa3ab8254c.bw2package",
            "IMPACT World+ v2.2.1",
            "IMPACT World+ v2.2.1",
        )
        _import_method_package(
            regio,
            "data/EF/EF31_regionalized-for-ecoinvent-v310.87ec66ed7e5775d0132d1129fb5caf03.bw2package",
            "EF v3.1",
            "EF v3.1",
        )
        _import_method_package(
            regio,
            "data/ReCiPe/ReCiPe_regionalized-for-ecoinvent-v310.dd7e66b1994d898394e3acfbed8eef83.bw2package",
            "ReCiPe 2016 v1.03 (H)",
            "ReCiPe 2016 v1.03 (H)",
        )

    elif lcia_method == "IW v2.2.1" and regio.ecoinvent_version == "3.12":
        regio.logger.info(
            "Importing the fully regionalized version of IMPACT World+ v2.2.1 for ecoinvent3.12."
        )

        _import_method_package(
            regio,
            "data/IW/impact_world_plus_221_regionalized-for-ecoinvent-v312.10af03e7ebbf7434cc89b2f3dafde784.bw2package",
            "IMPACT World+ v2.2.1",
            "IMPACT World+ v2.2.1",
        )

    elif lcia_method == "IW v2.2.1" and regio.ecoinvent_version == "3.11":
        regio.logger.info(
            "Importing the fully regionalized version of IMPACT World+ v2.2.1 for ecoinvent3.11."
        )

        _import_method_package(
            regio,
            "data/IW/impact_world_plus_221_regionalized-for-ecoinvent-v311.6674794954d1b190e85f28b287389bab.bw2package",
            "IMPACT World+ v2.2.1",
            "IMPACT World+ v2.2.1",
        )

    elif lcia_method == "IW v2.2.1" and regio.ecoinvent_version == "3.10":
        regio.logger.info(
            "Importing the fully regionalized version of IMPACT World+ v2.2.1 for ecoinvent3.10."
        )

        _import_method_package(
            regio,
            "data/IW/impact_world_plus_221_regionalized-for-ecoinvent-v310.e9543c08fd29c637c1b24faa3ab8254c.bw2package",
            "IMPACT World+ v2.2.1",
            "IMPACT World+ v2.2.1",
        )

    elif lcia_method == "EF v3.1" and regio.ecoinvent_version == "3.12":
        regio.logger.info("Importing the fully regionalized version of EF v3.1 for ecoinvent 3.12.")

        _import_method_package(
            regio,
            "data/EF/EF31_regionalized-for-ecoinvent-v312.06629f91f6a9326caa9145ff3a554e5a.bw2package",
            "EF v3.1",
            "EF v3.1",
        )

    elif lcia_method == "EF v3.1" and regio.ecoinvent_version == "3.11":
        regio.logger.info("Importing the fully regionalized version of EF v3.1 for ecoinvent 3.11.")

        _import_method_package(
            regio,
            "data/EF/EF31_regionalized-for-ecoinvent-v311.bdc82d0c5585c24e5558c33b468d8b7c.bw2package",
            "EF v3.1",
            "EF v3.1",
        )

    elif lcia_method == "EF v3.1" and regio.ecoinvent_version == "3.10":
        regio.logger.info("Importing the fully regionalized version of EF v3.1 for ecoinvent 3.10.")

        _import_method_package(
            regio,
            "data/EF/EF31_regionalized-for-ecoinvent-v310.87ec66ed7e5775d0132d1129fb5caf03.bw2package",
            "EF v3.1",
            "EF v3.1",
        )

    elif lcia_method == "ReCiPe 2016 v1.03 (H)" and regio.ecoinvent_version == "3.12":
        regio.logger.info(
            "Importing the fully regionalized version of ReCiPe 2016 v1.03 (H) for ecoinvent 3.12."
        )

        _import_method_package(
            regio,
            "data/ReCiPe/ReCiPe_regionalized-for-ecoinvent-v312.b0a09c06a9dce92251062e2e65ccda54.bw2package",
            "ReCiPe 2016 v1.03 (H)",
            "ReCiPe 2016 v1.03 (H)",
        )

    elif lcia_method == "ReCiPe 2016 v1.03 (H)" and regio.ecoinvent_version == "3.11":
        regio.logger.info(
            "Importing the fully regionalized version of ReCiPe 2016 v1.03 (H) for ecoinvent 3.11."
        )

        _import_method_package(
            regio,
            "data/ReCiPe/ReCiPe_regionalized-for-ecoinvent-v311.65e67dc615f8a7f38dbdf2d32009c9d8.bw2package",
            "ReCiPe 2016 v1.03 (H)",
            "ReCiPe 2016 v1.03 (H)",
        )

    elif lcia_method == "ReCiPe 2016 v1.03 (H)" and regio.ecoinvent_version == "3.10":
        regio.logger.info(
            "Importing the fully regionalized version of ReCiPe 2016 v1.03 (H) for ecoinvent 3.10."
        )

        _import_method_package(
            regio,
            "data/ReCiPe/ReCiPe_regionalized-for-ecoinvent-v310.dd7e66b1994d898394e3acfbed8eef83.bw2package",
            "ReCiPe 2016 v1.03 (H)",
            "ReCiPe 2016 v1.03 (H)",
        )
