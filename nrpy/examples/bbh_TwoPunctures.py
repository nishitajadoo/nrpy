"""
Sets up a complete C code project for generating binary black hole
  initial data using TwoPunctures.

Author: Zachariah B. Etienne
        zachetie **at** gmail **dot* com
"""
#########################################################
# STEP 1: Import needed Python modules, then set codegen
#         and compile-time parameters.
import shutil
import os
from inspect import currentframe as cfr
from types import FrameType as FT
from typing import cast, Union
from pathlib import Path

import nrpy.c_function as cfc
import nrpy.params as par
from nrpy.helpers import simd
import nrpy.helpers.parallel_codegen as pcg

import nrpy.infrastructures.BHaH.general_relativity.TwoPunctures.TwoPunctures_lib as TPl
import nrpy.infrastructures.BHaH.general_relativity.BSSN_C_codegen_library as BCl
import nrpy.infrastructures.BHaH.general_relativity.NRPyPN_quasicircular_momenta as NRPyPNqm
import nrpy.infrastructures.BHaH.simple_loop as lp
import nrpy.infrastructures.BHaH.CurviBoundaryConditions.CurviBoundaryConditions as cbc
import nrpy.infrastructures.BHaH.CodeParameters as CPs
import nrpy.infrastructures.BHaH.main_c as main
from nrpy.infrastructures.BHaH import rfm_precompute
import nrpy.infrastructures.BHaH.BHaH_defines_h as Bdefines_h
import nrpy.infrastructures.BHaH.Makefile_helpers as Makefile
import nrpy.infrastructures.BHaH.cmdline_input_and_parfiles as cmdpar
import nrpy.infrastructures.BHaH.numerical_grids_and_timestep as numericalgrids
import nrpy.infrastructures.BHaH.xx_tofrom_Cart as xxCartxx
from nrpy.infrastructures.BHaH.MoLtimestepping import MoL

par.set_parval_from_str("Infrastructure", "BHaH")

# Code-generation-time parameters:
project_name = "bbh_TwoPunctures"
IDtype = "TP_Interp"
IDCoordSystem = "Cartesian"
BBH_ID_choice = "GW150914ET"
grid_physical_size = 10.0
LapseEvolutionOption = "OnePlusLog"
ShiftEvolutionOption = "GammaDriving2ndOrder_Covariant"
GammaDriving_eta = 1.0
diagnostics_output_every = 0.25
t_final = 0.5 * diagnostics_output_every

CoordSystem = "SinhSpherical"
Nxx_dict = {
    "SinhSpherical": [128, 64, 2],
}
MoL_method = "RK4"  # MoL activated to set up gridfunctions for us.
OMP_collapse = 1
if "Spherical" in CoordSystem:
    par.set_parval_from_str("symmetry_axes", "2")
    par.adjust_CodeParam_default("CFL_FACTOR", 1.0)
    OMP_collapse = 2  # about 2x faster
    if CoordSystem == "SinhSpherical":
        sinh_width = 0.2
enable_rfm_precompute = True
fd_order = 8
radiation_BC_fd_order = 2
enable_simd = True
enable_fd_functions = True
enable_RbarDD_gridfunctions = True
parallel_codegen_enable = True
enable_KreissOliger_dissipation = False
boundary_conditions_desc = "outgoing radiation"

project_dir = os.path.join("project", project_name)

# First clean the project directory, if it exists.
shutil.rmtree(project_dir, ignore_errors=True)

par.set_parval_from_str("parallel_codegen_enable", parallel_codegen_enable)
par.set_parval_from_str("fd_order", fd_order)
par.set_parval_from_str("enable_RbarDD_gridfunctions", enable_RbarDD_gridfunctions)
par.set_parval_from_str("CoordSystem_to_register_CodeParameters", CoordSystem)

par.adjust_CodeParam_default("t_final", t_final)


#########################################################
# STEP 2: Declare core C functions & register each to
#         cfc.CFunction_dict["function_name"]
def register_CFunction_diagnostics(
    in_CoordSystem: str, plane: str = "yz"
) -> Union[None, pcg.NRPyEnv_type]:
    """
    Register C function for simulation diagnostics.

    :param in_CoordSystem: Specifies the coordinate system for the diagnostics.
    :param plane: The default plane for diagnostics; defaults to "yz".
    :return: None
    """
    if pcg.pcg_registration_phase():
        pcg.register_func_call(f"{__name__}.{cast(FT, cfr()).f_code.co_name}", locals())
        return None
    _ = par.CodeParameter(
        "REAL",
        __name__,
        "diagnostics_output_every",
        diagnostics_output_every,
        commondata=True,
    )

    includes = ["BHaH_defines.h", "BHaH_function_prototypes.h"]

    desc = r"""Diagnostics."""
    c_type = "void"
    name = "diagnostics"
    params = (
        "commondata_struct *restrict commondata, griddata_struct *restrict griddata"
    )

    body = r"""
const REAL currtime = commondata->time, currdt = commondata->dt, outevery = commondata->diagnostics_output_every;
// Explanation of the if() below:
// Step 1: round(currtime / outevery) rounds to the nearest integer multiple of currtime.
// Step 2: Multiplying by outevery yields the exact time we should output again, t_out.
// Step 3: If fabs(t_out - currtime) < 0.5 * currdt, then currtime is as close to t_out as possible!
if(fabs(round(currtime / outevery) * outevery - currtime) < 0.5*currdt) {
  for (int grid = 0; grid < commondata->NUMGRIDS; grid++) {
    // Unpack griddata struct:
    const REAL *restrict y_n_gfs = griddata[grid].gridfuncs.y_n_gfs;
    REAL *restrict auxevol_gfs = griddata[grid].gridfuncs.auxevol_gfs;
    REAL *restrict diagnostic_output_gfs = griddata[grid].gridfuncs.diagnostic_output_gfs;
    REAL *restrict xx[3];
    {
      for (int ww = 0; ww < 3; ww++)
        xx[ww] = griddata[grid].xx[ww];
    }
    params_struct *restrict params = &griddata[grid].params;
#include "set_CodeParameters.h"

    // Constraint output
    {
      Ricci_eval(commondata, params, &griddata->rfmstruct, y_n_gfs, auxevol_gfs);
      constraints_eval(commondata, params, &griddata->rfmstruct, y_n_gfs, auxevol_gfs, diagnostic_output_gfs);
    }
    // 0D output
    {
      char filename[256];
      sprintf(filename, "out0d-conv_factor%.2f.txt", convergence_factor);
      FILE *outfile;
      if (nn == 0)
        outfile = fopen(filename, "w");
      else
        outfile = fopen(filename, "a");
      if (outfile == NULL) {
        fprintf(stderr, "Error: Cannot open file %s for writing.\n", filename);
        exit(1);
      }

      const int r_mid_idx = IDX3(Nxx_plus_2NGHOSTS1 / 2, Nxx_plus_2NGHOSTS1 / 2, Nxx_plus_2NGHOSTS2 / 2);

      const REAL H_at_center = diagnostic_output_gfs[IDX4pt(HGF, r_mid_idx)];
      const REAL M2_at_center = diagnostic_output_gfs[IDX4pt(MSQUAREDGF, r_mid_idx)];
      const REAL cf_at_center = y_n_gfs[IDX4pt(CFGF, r_mid_idx)];
      const REAL alpha_at_center = y_n_gfs[IDX4pt(ALPHAGF, r_mid_idx)];
      const REAL trK_at_center = y_n_gfs[IDX4pt(TRKGF, r_mid_idx)];

      fprintf(outfile, "%e %e %e %e %e %e\n", time, log10(fabs(H_at_center + 1e-16)), log10(fabs(M2_at_center + 1e-16)), cf_at_center, alpha_at_center, trK_at_center);

      fclose(outfile);
    }

    // 1D output
    {
      char filename[256];
      sprintf(filename, "out1d-conv_factor%.2f-t%08.2f.txt", convergence_factor, time);
      FILE *outfile;
      outfile = fopen(filename, "w");
      if (outfile == NULL) {
        fprintf(stderr, "Error: Cannot open file %s for writing.\n", filename);
        exit(1);
      }
      for (int i1 = Nxx_plus_2NGHOSTS1 - NGHOSTS - 1; i1 >= NGHOSTS; i1 -= Nxx1-1) {
        int i0_start, i0_end, i0_step;

        if (i1 == (Nxx_plus_2NGHOSTS1 - NGHOSTS - 1)) {
          i0_start = Nxx_plus_2NGHOSTS0 - NGHOSTS - 1;
          i0_end = NGHOSTS - 1;
          i0_step = -1;
        } else if (i1 == NGHOSTS) {
          i0_start = NGHOSTS;
          i0_end = Nxx_plus_2NGHOSTS0 - NGHOSTS;
          i0_step = 1;
        } else {
          continue; // Skip this iteration if i1 is not one of the special values
        }

        for (int i0 = i0_start; i0 != i0_end; i0 += i0_step) {
          const int i2 = Nxx_plus_2NGHOSTS2 / 2;
          const int idx3 = IDX3(i0, i1, i2);
          REAL xCart[3];
          xx_to_Cart(commondata, params, xx, i0, i1, i2, xCart);

          const REAL alphaL = y_n_gfs[IDX4pt(ALPHAGF, idx3)];
          const REAL cfL = y_n_gfs[IDX4pt(CFGF, idx3)];
          const REAL trKL = y_n_gfs[IDX4pt(TRKGF, idx3)];
          const REAL HL = diagnostic_output_gfs[IDX4pt(HGF, idx3)];
          const REAL M2L = diagnostic_output_gfs[IDX4pt(MSQUAREDGF, idx3)];

          fprintf(outfile, "%e %e %e %e %e %e\n", xCart[2], log10(fabs(HL + 1e-16)), log10(fabs(M2L + 1e-16)), cfL, alphaL, trKL);
        }
      }
      fclose(outfile);
    }
"""
    body += rf"""
    // 2D output:
    {{
      char filename[256];
      sprintf(filename, "out2d-{plane}_plane-conv_factor%.2f-t%08.2f.txt", convergence_factor, time);
      FILE *outfile;
      outfile = fopen(filename, "w");
      if (outfile == NULL) {{
        fprintf(stderr, "Error: Cannot open file %s for writing.\n", filename);
        exit(1);
      }}
"""
    body += lp.simple_loop_2D(
        loop_body=r"""
const int idx3 = IDX3(i0, i1, i2);
REAL xCart[3];
xx_to_Cart(commondata, params, xx, i0, i1, i2, xCart);

const REAL alphaL = y_n_gfs[IDX4pt(ALPHAGF, idx3)];
const REAL cfL = y_n_gfs[IDX4pt(CFGF, idx3)];
const REAL trKL = y_n_gfs[IDX4pt(TRKGF, idx3)];
const REAL HL = diagnostic_output_gfs[IDX4pt(HGF, idx3)];
const REAL M2L = diagnostic_output_gfs[IDX4pt(MSQUAREDGF, idx3)];

fprintf(outfile, "%e %e %e %e %e %e %e %e\n", xCart[0], xCart[1], xCart[2], log10(fabs(HL + 1e-16)), log10(fabs(M2L + 1e-16)), cfL, alphaL, trKL);
""",
        CoordSystem=in_CoordSystem,
        plane=plane,
    )
    body += r"""
      fclose(outfile);
    }
  }
}
if(commondata->time + commondata->dt > commondata->t_final) printf("\n");
"""

    cfc.register_CFunction(
        includes=includes,
        desc=desc,
        c_type=c_type,
        name=name,
        params=params,
        include_CodeParameters_h=False,
        body=body,
    )
    return cast(pcg.NRPyEnv_type, pcg.NRPyEnv())


NRPyPNqm.register_CFunction_NRPyPN_quasicircular_momenta()
TPl.register_C_functions()
BCl.register_CFunction_initial_data(
    CoordSystem=CoordSystem,
    IDtype=IDtype,
    IDCoordSystem=IDCoordSystem,
    ID_persist_struct_str=TPl.ID_persist_str(),
    populate_ID_persist_struct_str=r"""
initialize_ID_persist_struct(commondata, &ID_persist);
TP_solve(&ID_persist);
""",
    free_ID_persist_struct_str=r"""
{
  extern void free_derivs (derivs * v, int n);  // <- Needed to free memory allocated by TwoPunctures.
  // <- Free memory allocated within ID_persist.
  // Now that we're finished with par.v and par.cf_v (needed in setting up ID, we can free up memory for TwoPunctures' grids...
  free_derivs (&ID_persist.v,    ID_persist.npoints_A * ID_persist.npoints_B * ID_persist.npoints_phi);
  free_derivs (&ID_persist.cf_v, ID_persist.npoints_A * ID_persist.npoints_B * ID_persist.npoints_phi);
}
""",
)

numericalgrids.register_CFunction_numerical_grids_and_timestep_setup(
    CoordSystem, grid_physical_size, Nxx_dict
)
register_CFunction_diagnostics(in_CoordSystem=CoordSystem)
if enable_rfm_precompute:
    rfm_precompute.register_CFunctions_rfm_precompute(CoordSystem)
BCl.register_CFunction_rhs_eval(
    CoordSystem=CoordSystem,
    enable_rfm_precompute=enable_rfm_precompute,
    enable_simd=enable_simd,
    enable_fd_functions=enable_fd_functions,
    enable_KreissOliger_dissipation=enable_KreissOliger_dissipation,
    LapseEvolutionOption=LapseEvolutionOption,
    ShiftEvolutionOption=ShiftEvolutionOption,
    OMP_collapse=OMP_collapse,
)
BCl.register_CFunction_Ricci_eval(
    CoordSystem=CoordSystem,
    enable_rfm_precompute=enable_rfm_precompute,
    enable_simd=enable_simd,
    enable_fd_functions=enable_fd_functions,
    OMP_collapse=OMP_collapse,
)
BCl.register_CFunction_enforce_detgammabar_equals_detgammahat(
    CoordSystem=CoordSystem,
    enable_rfm_precompute=enable_rfm_precompute,
    enable_fd_functions=enable_fd_functions,
    OMP_collapse=OMP_collapse,
)
BCl.register_CFunction_constraints(
    CoordSystem=CoordSystem,
    enable_rfm_precompute=enable_rfm_precompute,
    enable_simd=enable_simd,
    enable_fd_functions=enable_fd_functions,
    OMP_collapse=OMP_collapse,
)

if __name__ == "__main__" and parallel_codegen_enable:
    pcg.do_parallel_codegen()

cbc.CurviBoundaryConditions_register_C_functions(
    CoordSystem, radiation_BC_fd_order=radiation_BC_fd_order
)
MoL.MoL_register_CFunctions(
    MoL_method=MoL_method,
    rhs_string="",
    post_rhs_string="",
    enable_rfm_precompute=enable_rfm_precompute,
    enable_curviBCs=True,
)
xxCartxx.register_CFunction__Cart_to_xx_and_nearest_i0i1i2(CoordSystem)
xxCartxx.register_CFunction_xx_to_Cart(CoordSystem)

# Reset CodeParameter defaults according to variables set above.
if CoordSystem == "SinhSpherical":
    par.adjust_CodeParam_default("SINHW", sinh_width)
par.adjust_CodeParam_default("eta", GammaDriving_eta)


#########################################################
# STEP 3: Generate header files, register C functions and
#         command line parameters, set up boundary conditions,
#         and create a Makefile for this project.
#         Project is output to project/[project_name]/
CPs.write_CodeParameters_h_files(project_dir=project_dir)
CPs.register_CFunctions_params_commondata_struct_set_to_default()
cmdpar.generate_default_parfile(project_dir=project_dir, project_name=project_name)
cmdpar.register_CFunction_cmdline_input_and_parfile_parser(
    project_name=project_name,
    cmdline_inputs=[
        "initial_sep",
        "mass_ratio",
        "bbhxy_BH_M_chix",
        "bbhxy_BH_M_chiy",
        "bbhxy_BH_M_chiz",
        "bbhxy_BH_m_chix",
        "bbhxy_BH_m_chiy",
        "bbhxy_BH_m_chiz",
    ],
)
TPl.copy_TwoPunctures_header_files(TwoPunctures_Path=Path(project_dir) / "TwoPunctures")
Bdefines_h.output_BHaH_defines_h(
    additional_includes=[str(Path("TwoPunctures") / Path("TwoPunctures.h"))],
    project_dir=project_dir,
    fin_NGHOSTS_add_one_for_upwinding=True,
    enable_simd=enable_simd,
    CoordSystem=CoordSystem,
)

main.register_CFunction_main_c(
    initial_data_desc=IDtype,
    MoL_method=MoL_method,
    enable_rfm_precompute=enable_rfm_precompute,
    enable_CurviBCs=True,
    boundary_conditions_desc=boundary_conditions_desc,
)

if enable_simd:
    simd.copy_simd_intrinsics_h(project_dir=project_dir)

Makefile.output_CFunctions_function_prototypes_and_construct_Makefile(
    project_dir=project_dir,
    project_name=project_name,
    exec_name=project_name,
    addl_libraries=["-lgsl", "-lgslcblas"],
)
print(
    f"Finished! Now go into project/{project_name} and type `make` to build, then ./{project_name} to run."
)
print(f"    Parameter file can be found in {project_name}.par")
