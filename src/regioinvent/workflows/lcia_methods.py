from importlib.resources import as_file, files
from bw2io.strategies.generic import link_iterable_by_fields
from tqdm import tqdm
import bw2data as bd
import bw2io as bi
import numpy as np


def _has_method_family(method_fragment):
    if 'ReCiPe' in method_fragment:
        return any(method for method in bd.methods if "regionalized" in method[0] and "ReCiPe 2016 v1.03" in method[0])
    elif 'EF' in method_fragment:
        return any(method for method in bd.methods if "regionalized" in method[0] and "EF v3.1" in method[0])
    elif 'GLAM' in method_fragment:
        return any(method for method in bd.methods if "regionalized" in method[0] and "GLAM Version 1.1.2026.06.24beta" in method[0])
    elif 'IMPACT World+' in method_fragment:
        # TODO don't forget to update version number of IW+ in list comprehension
        return any(method for method in bd.methods if "regionalized" in method[0] and "IMPACT World+" in method[0] and
                   "2.2.1" in method[0])


def _import_method_excel(regio, method_abbreviation, method_fragment, label):
    if _has_method_family(method_fragment):
        regio.logger.info(f"Regionalized {label} already present in Brightway project; skipping import.")
        return

    # check the bw2data version being used
    version_raw = bd.__version__
    if isinstance(version_raw, tuple):
        major_version = version_raw[0]
    else:
        major_version = int(str(version_raw).split('.')[0])

    method_folder = files('regioinvent') / 'data' / method_abbreviation / f'ei{regio.ecoinvent_version}'

    virtual_files = [f for f in method_folder.iterdir() if f.is_file() if f.name != '__init__.py']

    for virtual_file in tqdm(virtual_files):
        file_name = virtual_file.name
        if method_abbreviation == 'IW':
            method_name = ('_'.join(file_name.split('_')[:2]), file_name.split('_')[2], file_name.split('_')[3])
        elif method_abbreviation in ['EF', 'ReCiPe', 'GLAM']:
            method_name = (file_name.split('_')[0], file_name.split('_')[1], file_name.split('_')[2])

        unit = file_name.split('_')[-1].split('.xlsx')[0]

        with as_file(virtual_file) as physical_file_path:
            imp = bi.ExcelLCIAImporter(
                filepath=physical_file_path,
                name=method_name,
                description='This is the regionalized version of ' + method_name[0],
                unit=unit
            )
            imp.apply_strategies(verbose=False)
            if not list(imp.unlinked):
                imp.write_methods(verbose=False)
            # if there are still unlinked, that means we must match with the spatialized biosphere database too
            else:
                if major_version >= 4:
                    link_iterable_by_fields(imp.data, other=bd.Database(regio.name_spatialized_biosphere),
                                            fields=['name', 'categories'], edge_kinds=["biosphere"])
                else:
                    link_iterable_by_fields(imp.data, other=bd.Database(regio.name_spatialized_biosphere),
                                            fields=['name', 'categories'], kind=["biosphere"])
                imp.write_methods(verbose=False)


def import_fully_regionalized_impact_method(regio, lcia_method="all"):
    """
    Function to import a fully regionalized impact method into your brightway project, to-be-used with the
    spatialized version of ecoinvent. You can choose between IMPACT World+, EF and ReCiPe, or simply all of them.

    :param lcia_method: [str] the name of the LCIA method to be imported to be used with the spatialized ecoinvent,
                            available methods are "IW v2.2.1", "EF v3.1", "ReCiPe 2016 v1.03 (H)" or "all".
    :return:
    """

    if lcia_method not in ["IW v2.2.1",
                           "EF v3.1",
                           "ReCiPe 2016 v1.03 (H)",
                           # "GLAM Version 1.1.2026.06.24beta",
                           "all"]:
        raise KeyError(
            "Available LCIA methods are: 'IW v2.2.1', 'EF v3.1', 'ReCiPe 2016 v1.03 (H)', "
            # "'GLAM Version 1.1.2026.06.24beta'"
            " or 'all'"
        )

    # Compatibility for older Brightway code paths that still reference np.NaN.
    if not hasattr(np, "NaN"):
        np.NaN = np.nan

    if lcia_method == 'all':
        regio.logger.info(f"Importing regionalized version of IW+ v2.2.1.")
        _import_method_excel(
            regio,
            'IW',
            "IMPACT World+ v2.2.1",
            "IMPACT World+ v2.2.1",
        )

        regio.logger.info(f"Importing regionalized version of EF v3.1.")

        _import_method_excel(
            regio,
            'EF',
            "EF v3.1",
            "EF v3.1",
        )

        regio.logger.info(f"Importing regionalized version of ReCiPe 2016 v1.03 (H).")

        _import_method_excel(
            regio,
            'ReCiPe',
            "ReCiPe 2016 v1.03 (H)",
            "ReCiPe 2016 v1.03 (H)",
        )

        # regio.logger.info(f"Importing regionalized version of GLAM Version 1.1.2026.06.24beta.")
        #
        # _import_method_excel(
        #     regio,
        #     'GLAM',
        #     "GLAM Version 1.1.2026.06.24beta",
        #     "GLAM Version 1.1.2026.06.24beta",
        # )

    elif lcia_method == "IW v2.2.1":

        regio.logger.info(f"Importing regionalized version of IW+ v2.2.1.")

        _import_method_excel(
            regio,
            'IW',
            "IMPACT World+ v2.2.1",
            "IMPACT World+ v2.2.1",
        )

    elif lcia_method == "EF v3.1":

        regio.logger.info(f"Importing regionalized version of EF v3.1.")

        _import_method_excel(
            regio,
            'EF',
            "EF v3.1",
            "EF v3.1",
        )

    elif lcia_method == "ReCiPe 2016 v1.03 (H)":

        regio.logger.info(f"Importing regionalized version of ReCiPe 2016 v1.03 (H).")

        _import_method_excel(
            regio,
            'ReCiPe',
            "ReCiPe 2016 v1.03 (H)",
            "ReCiPe 2016 v1.03 (H)",
        )

    elif lcia_method == "GLAM Version 1.1.2026.06.24beta":
        print("GLAM Version 1.1.2026.06.24beta not available yet. Need confirmation by GLAM team.")

        # regio.logger.info(f"Importing regionalized version of GLAM Version 1.1.2026.06.24beta.")
        #
        # _import_method_excel(
        #     regio,
        #     'GLAM',
        #     "GLAM Version 1.1.2026.06.24beta",
        #     "GLAM Version 1.1.2026.06.24beta",
        # )
