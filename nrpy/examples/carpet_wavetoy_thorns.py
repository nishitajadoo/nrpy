"""
Generates Einstein Toolkit thorns for solving the wave equation on Cartesian AMR grids with Carpet.

Author: Zachariah B. Etienne
        zachetie **at** gmail **dot* com
"""

#########################################################
# STEP 1: Import needed Python modules, then set codegen
#         and compile-time parameters.
from typing import Union, cast, List
from inspect import currentframe as cfr
from types import FrameType as FT
import shutil
import os

import nrpy.params as par
import nrpy.c_function as cfc
import nrpy.grid as gri
import nrpy.c_codegen as ccg
import nrpy.helpers.parallel_codegen as pcg
from nrpy.equations.wave_equation.InitialData import InitialData
from nrpy.equations.wave_equation.WaveEquation_RHSs import WaveEquation_RHSs
import nrpy.infrastructures.ETLegacy.simple_loop as lp
from nrpy.infrastructures.ETLegacy import boundary_conditions
from nrpy.infrastructures.ETLegacy import CodeParameters
from nrpy.infrastructures.ETLegacy import make_code_defn
from nrpy.infrastructures.ETLegacy import MoL_registration
from nrpy.infrastructures.ETLegacy import set_rhss_to_zero
from nrpy.infrastructures.ETLegacy import Symmetry_registration
from nrpy.infrastructures.ETLegacy import schedule_ccl
from nrpy.infrastructures.ETLegacy import interface_ccl
from nrpy.infrastructures.ETLegacy import param_ccl


par.set_parval_from_str("Infrastructure", "ETLegacy")

# Code-generation-time parameters:
project_name = "et_wavetoy"
ID_thorn_name = "IDWaveToyNRPy"
diag_thorn_name = "diagWaveToyNRPy"
evol_thorn_name = "WaveToyNRPy"
WaveType = "SphericalGaussian"
default_sigma = 3.0
grid_physical_size = 10.0
t_final = 0.8 * grid_physical_size
default_diagnostics_output_every = 0.5
default_checkpoint_every = 50.0
enable_rfm_precompute = False
MoL_method = "RK4"
fd_order = 8
enable_simd = True
parallel_codegen_enable = True
CoordSystem = "Cartesian"
OMP_collapse = 1

project_dir = os.path.join("project", project_name)

# First clean the project directory, if it exists.
shutil.rmtree(project_dir, ignore_errors=True)

par.set_parval_from_str("parallel_codegen_enable", parallel_codegen_enable)
par.set_parval_from_str("fd_order", fd_order)
standard_ET_includes = ["math.h", "cctk.h", "cctk_Arguments.h", "cctk_Parameters.h"]


#########################################################
# STEP 2: Declare core C functions & register each to
#         cfc.CFunction_dict["function_name"]
def register_CFunction_exact_solution_single_point(
    thorn_name: str = "",
    in_WaveType: str = "SphericalGaussian",
    in_default_sigma: float = 3.0,
    default_k0: float = 1.0,
    default_k1: float = 1.0,
    default_k2: float = 1.0,
) -> Union[None, pcg.NRPyEnv_type]:
    """
    Register a C function for the exact solution at a single point.

    :param thorn_name: The Einstein Toolkit thorn name.
    :param in_WaveType: The type of wave: SphericalGaussian or PlaneWave
    :param in_default_sigma: The default value for the Gaussian width (sigma).
    :param default_k0: The default value for the plane wave wavenumber k in the x-direction
    :param default_k1: The default value for the plane wave wavenumber k in the y-direction
    :param default_k2: The default value for the plane wave wavenumber k in the z-direction
    :return: None if in registration phase, else the updated NRPy environment.
    """
    if pcg.pcg_registration_phase():
        pcg.register_func_call(f"{__name__}.{cast(FT, cfr()).f_code.co_name}", locals())
        return None
    # Populate uu_ID, vv_ID
    ID = InitialData(
        WaveType=in_WaveType,
        default_sigma=in_default_sigma,
        default_k0=default_k0,
        default_k1=default_k1,
        default_k2=default_k2,
    )

    includes = standard_ET_includes

    desc = r"""Exact solution at a single point."""
    c_type = "void"
    name = f"WaveToy_exact_solution_single_point"
    params = r"""const CCTK_REAL xx, const CCTK_REAL yy, const CCTK_REAL zz, CCTK_REAL *restrict exact_soln_UUGF, CCTK_REAL *restrict exact_soln_VVGF"""
    body = f"DECLARE_CCTK_PARAMETERS\n"
    body += ccg.c_codegen(
        [ID.uu_ID, ID.vv_ID],
        ["*exact_soln_UUGF", "*exact_soln_VVGF"],
        verbose=False,
        include_braces=False,
    )
    cfc.register_CFunction(
        subdirectory=thorn_name,
        includes=includes,
        desc=desc,
        c_type=c_type,
        name=name,
        params=params,
        include_CodeParameters_h=True,
        body=body,
        ET_current_thorn_CodeParams_used=["k0", "k1", "k2", "sigma"],
    )
    return cast(pcg.NRPyEnv_type, pcg.NRPyEnv())


def register_CFunction_exact_solution_all_points(
    thorn_name: str = "",
) -> Union[None, pcg.NRPyEnv_type]:
    """
    Register a C function for the exact solution at a single point.

    :param thorn_name: The Einstein Toolkit thorn name.
    :return: None if in registration phase, else the updated NRPy environment.
    """
    if pcg.pcg_registration_phase():
        pcg.register_func_call(f"{__name__}.{cast(FT, cfr()).f_code.co_name}", locals())
        return None
    includes = standard_ET_includes

    gri.register_gridfunctions(["uu_exact", "vv_exact"], group="AUX")
    desc = r"""Set the exact solution at all grid points."""
    c_type = "void"
    name = f"{thorn_name}_exact_solution_all_points"
    params = "CCTK_ARGUMENTS"
    body = f"DECLARE_CCTK_PARAMETERS\n"

    x_gf_access = gri.ETLegacyGridFunction.access_gf("x")
    y_gf_access = gri.ETLegacyGridFunction.access_gf("y")
    z_gf_access = gri.ETLegacyGridFunction.access_gf("z")
    uu_exact_gf_access = gri.ETLegacyGridFunction.access_gf("uu_exact")
    vv_exact_gf_access = gri.ETLegacyGridFunction.access_gf("vv_exact")
    if thorn_name == ID_thorn_name:
        uu_exact_gf_access = gri.ETLegacyGridFunction.access_gf("uu")
        vv_exact_gf_access = gri.ETLegacyGridFunction.access_gf("vv")
    body += lp.simple_loop(
        f"WaveToy_exact_solution_single_point({x_gf_access}, {y_gf_access}, {z_gf_access}, &{uu_exact_gf_access}, {vv_exact_gf_access});\n",
        loop_region="all points",
    )

    bin = "CCTK_INITIAL"
    if thorn_name == diag_thorn_name:
        bin = "CCTK_ANALYSIS"
    ET_schedule_bin_entry = (
        bin,
        f"""
schedule FUNC_NAME IN {bin}
{{
  LANG: C
  READS: Grid::x(Everywhere)
  READS: Grid::y(Everywhere)
  READS: Grid::z(Everywhere)
  WRITES: {evol_thorn_name}::uu(Everywhere)
  WRITES: {evol_thorn_name}::vv(Everywhere)
}} "Set up metric fields for binary black hole initial data"
""",
    )
    cfc.register_CFunction(
        subdirectory=thorn_name,
        includes=includes,
        desc=desc,
        c_type=c_type,
        name=name,
        params=params,
        body=body,
        ET_thorn_name=thorn_name,
        ET_schedule_bins_entries=[ET_schedule_bin_entry],
    )
    return cast(pcg.NRPyEnv_type, pcg.NRPyEnv())


def register_CFunction_rhs_eval(thorn_name: str) -> Union[None, pcg.NRPyEnv_type]:
    """
    Register the right-hand side evaluation function for the wave equation with specific parameters.

    :param thorn_name: The name of the thorn for which the right-hand side evaluation function is being registered.
    :return: None if in registration phase, else the updated NRPy environment.
    """
    if pcg.pcg_registration_phase():
        pcg.register_func_call(f"{__name__}.{cast(FT, cfr()).f_code.co_name}", locals())
        return None

    includes = standard_ET_includes
    if enable_simd:
        includes += [os.path.join("simd", "simd_intrinsics.h")]
    desc = r"""Set RHSs for wave equation."""
    c_type = "void"
    name = f"{thorn_name}_rhs_eval"
    params = "CCTK_ARGUMENTS"
    # Populate uu_rhs, vv_rhs
    rhs = WaveEquation_RHSs()
    body = f"DECLARE_CCTK_ARGUMENTS_{name}\n"
    body += lp.simple_loop(
        loop_body=ccg.c_codegen(
            [rhs.uu_rhs, rhs.vv_rhs],
            [
                gri.ETLegacyGridFunction.access_gf("uu_rhs"),
                gri.ETLegacyGridFunction.access_gf("vv_rhs"),
            ],
            enable_fd_codegen=True,
            enable_simd=enable_simd,
        ),
        loop_region="interior",
        enable_simd=enable_simd,
    )
    ET_schedule_bin_entry = (
        "MoL_CalcRHS",
        """
schedule FUNC_NAME in MoL_CalcRHS as rhs_eval
{
  LANG: C
  READS: evol_variables(everywhere) #, auxevol_variables(interior)
  WRITES: evol_variables_rhs(interior)
} "MoL: Evaluate WaveToy RHSs"
""",
    )

    cfc.register_CFunction(
        subdirectory=thorn_name,
        include_CodeParameters_h=True,
        includes=includes,
        desc=desc,
        c_type=c_type,
        name=name,
        params=params,
        body=body,
        ET_thorn_name=thorn_name,
        ET_schedule_bins_entries=[ET_schedule_bin_entry],
    )
    return cast(pcg.NRPyEnv_type, pcg.NRPyEnv())


register_CFunction_exact_solution_single_point(
    thorn_name=ID_thorn_name, in_WaveType=WaveType, in_default_sigma=default_sigma
)
for thorn in [ID_thorn_name, diag_thorn_name]:
    register_CFunction_exact_solution_all_points(thorn_name=thorn)
register_CFunction_rhs_eval(thorn_name=evol_thorn_name)

if __name__ == "__main__" and parallel_codegen_enable:
    pcg.do_parallel_codegen()

########################
# STEP 2: Register functions that depend on all gridfunctions & CodeParameters having been set:

Symmetry_registration.register_CFunction_Symmetry_registration_oldCartGrid3D(
    thorn_name=evol_thorn_name
)
boundary_conditions.register_CFunctions(thorn_name=evol_thorn_name)
set_rhss_to_zero.register_CFunction_zero_rhss(thorn_name=evol_thorn_name)
if enable_simd:
    CodeParameters.write_CodeParameters_simd_h_files(
        project_dir=project_dir, thorn_name=evol_thorn_name
    )
MoL_registration.register_CFunction_MoL_registration(thorn_name=evol_thorn_name)

########################
# STEP 3: All functions have been registered at this point. Time to output the CCL files & thorns!

CParams_registered_to_params_ccl: List[str] = []

# CCL files: evol_thorn
schedule_ccl.construct_schedule_ccl(
    project_dir=project_dir,
    thorn_name=evol_thorn_name,
    STORAGE="""
STORAGE: evol_variables[3]     # Evolution variables
STORAGE: evol_variables_rhs[1] # Variables storing right-hand-sides
# STORAGE: aux_variables[3]      # Diagnostics variables
# STORAGE: auxevol_variables[1]  # Single-timelevel storage of variables needed for evolutions.
""",
)
interface_ccl.construct_interface_ccl(
    thorn_name=evol_thorn_name,
    project_dir=project_dir,
    inherits="Boundary Grid MethodofLines",
    USES_INCLUDEs="""USES INCLUDE: Symmetry.h
USES INCLUDE: Boundary.h
""",
    enable_NewRad=True,
    is_evol_thorn=True,
)
CParams_registered_to_params_ccl += param_ccl.construct_param_ccl(
    project_dir=project_dir,
    thorn_name=evol_thorn_name,
    shares_extends_str="",
)

# CCL files: ID_thorn


for thorn in [evol_thorn_name, ID_thorn_name, diag_thorn_name]:
    make_code_defn.output_CFunctions_and_construct_make_code_defn(
        project_dir=project_dir, thorn_name=thorn
    )

# print(
#     f"Finished! Now go into project/{project_name} and type `make` to build, then ./{project_name} to run."
# )
# print(f"    Parameter file can be found in {project_name}.par")
