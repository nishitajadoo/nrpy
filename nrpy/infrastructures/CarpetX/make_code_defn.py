"""
Output C functions and construct make.code.defn file.

Author: Zachariah B. Etienne
        zachetie **at** gmail **dot* com
"""

from pathlib import Path
from typing import List

import nrpy.c_function as cfc
from nrpy.helpers.conditional_file_updater import ConditionalFileUpdater


def output_CFunctions_and_construct_make_code_defn(
    project_dir: str, thorn_name: str
) -> None:
    """
    Generate and write the make.code.defn file for a specified thorn.

    This function goes through the C functions in `cfc.CFunction_dict`, filters
    those that belong to the given thorn, and sorts them by name. It then writes
    these sorted C functions to the make.code.defn file located in the thorn's
    'src' directory.

    :param project_dir: Project directory, usually "project/{arrangement of thorns directory}".
    :param thorn_name: Name of the thorn for which the make.code.defn file is generated.
    """
    # Initialize an empty list to collect CFunction objects belonging to the thorn
    make_code_defn_list_of_CFunctions: List[cfc.CFunction] = []

    # Filter out CFunctions belonging to the specified thorn and append to list
    for CFunction in cfc.CFunction_dict.values():
        if CFunction.subdirectory == thorn_name:
            make_code_defn_list_of_CFunctions.append(CFunction)

    # Sort the list of CFunctions by their name attribute
    make_code_defn_list_of_CFunctions.sort(key=lambda x: x.name)

    src_Path = Path(project_dir) / thorn_name / "src"
    src_Path.mkdir(parents=True, exist_ok=True)
    make_code_defn_file = src_Path / "make.code.defn"

    # Open and write to the make.code.defn file
    with ConditionalFileUpdater(make_code_defn_file) as make_code_defn:
        make_code_defn.write(f"# make.code.defn file for thorn {thorn_name}\n\n")
        make_code_defn.write("# Source files that need to be compiled:\n")
        make_code_defn.write("SRCS = \\\n")

        # Iterate through sorted list of CFunctions and write each to the make.code.defn file
        for i, CFunction in enumerate(make_code_defn_list_of_CFunctions):
            with ConditionalFileUpdater(
                src_Path / f"{CFunction.name}.cxx", encoding="utf-8"
            ) as file:
                file.write(CFunction.full_function)

            # If it's not the last iteration, append a backslash:
            if i < len(make_code_defn_list_of_CFunctions) - 1:
                make_code_defn.write(f"       {CFunction.name}.cxx \\\n")
            # If it's the last iteration, don't append a backslash:
            else:
                make_code_defn.write(f"       {CFunction.name}.cxx\n")
