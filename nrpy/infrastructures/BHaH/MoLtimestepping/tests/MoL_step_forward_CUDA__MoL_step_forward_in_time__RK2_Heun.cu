#include "BHaH_defines.h"
#include "BHaH_function_prototypes.h"
#include "intrinsics/cuda_intrinsics.h"

#define LOOP_ALL_GFS_GPS(ii)                                                                                                                         \
  const int tid0 = threadIdx.x + blockIdx.x * blockDim.x;                                                                                            \
  const int stride0 = blockDim.x * gridDim.x;                                                                                                        \
  for (int(ii) = (tid0);                                                                                                                             \
       (ii) < d_params[streamid].Nxx_plus_2NGHOSTS0 * d_params[streamid].Nxx_plus_2NGHOSTS1 * d_params[streamid].Nxx_plus_2NGHOSTS2 * NUM_EVOL_GFS;  \
       (ii) += (stride0))
/**
 * Kernel: rk_substep_1_gpu.
 * Compute RK substep 1.
 */
__global__ static void rk_substep_1_gpu(const size_t streamid, REAL *restrict k_odd_gfs, REAL *restrict y_n_gfs,
                                        REAL *restrict y_nplus1_running_total_gfs, const REAL dt) {
  LOOP_ALL_GFS_GPS(i) {
    const REAL k_odd_gfsL = k_odd_gfs[i];
    const REAL y_n_gfsL = y_n_gfs[i];
    static constexpr double dblRK_Rational_1_2 = 1.0 / 2.0;
    const REAL_CUDA_ARRAY RK_Rational_1_2 = ConstCUDA(dblRK_Rational_1_2);

    const REAL_CUDA_ARRAY __rk_exp_0 = MulCUDA(RK_Rational_1_2, MulCUDA(dt, k_odd_gfsL));
    const REAL_CUDA_ARRAY __rk_exp_1 = FusedMulAddCUDA(dt, k_odd_gfsL, y_n_gfsL);
    WriteCUDA(&y_nplus1_running_total_gfs[i], __rk_exp_0);
    WriteCUDA(&k_odd_gfs[i], __rk_exp_1);
  }
} // END FUNCTION rk_substep_1_gpu

/**
 * Runge-Kutta function for substep 1.
 */
static void rk_substep_1__launcher(params_struct *restrict params, REAL *restrict k_odd_gfs, REAL *restrict y_n_gfs,
                                   REAL *restrict y_nplus1_running_total_gfs, const REAL dt) {
  const int Nxx_plus_2NGHOSTS0 = params->Nxx_plus_2NGHOSTS0;
  const int Nxx_plus_2NGHOSTS1 = params->Nxx_plus_2NGHOSTS1;
  const int Nxx_plus_2NGHOSTS2 = params->Nxx_plus_2NGHOSTS2;
  MAYBE_UNUSED const int Ntot = Nxx_plus_2NGHOSTS0 * Nxx_plus_2NGHOSTS1 * Nxx_plus_2NGHOSTS2 * NUM_EVOL_GFS;

  const size_t threads_in_x_dir = BHAH_THREADS_IN_X_DIR_MOL_SUBSTEP;
  const size_t threads_in_y_dir = BHAH_THREADS_IN_Y_DIR_MOL_SUBSTEP;
  const size_t threads_in_z_dir = BHAH_THREADS_IN_Z_DIR_MOL_SUBSTEP;
  dim3 threads_per_block(threads_in_x_dir, threads_in_y_dir, threads_in_z_dir);
  dim3 blocks_per_grid((Ntot + threads_in_x_dir - 1) / threads_in_x_dir, 1, 1);
  size_t sm = 0;
  size_t streamid = params->grid_idx % NUM_STREAMS;
  rk_substep_1_gpu<<<blocks_per_grid, threads_per_block, sm, streams[streamid]>>>(streamid, k_odd_gfs, y_n_gfs, y_nplus1_running_total_gfs, dt);
  cudaCheckErrors(cudaKernel, "rk_substep_1_gpu failure");
} // END FUNCTION rk_substep_1__launcher

/**
 * Kernel: rk_substep_2_gpu.
 * Compute RK substep 2.
 */
__global__ static void rk_substep_2_gpu(const size_t streamid, REAL *restrict k_even_gfs, REAL *restrict y_n_gfs,
                                        REAL *restrict y_nplus1_running_total_gfs, const REAL dt) {
  LOOP_ALL_GFS_GPS(i) {
    const REAL k_even_gfsL = k_even_gfs[i];
    const REAL y_n_gfsL = y_n_gfs[i];
    const REAL y_nplus1_running_total_gfsL = y_nplus1_running_total_gfs[i];
    static constexpr double dblRK_Rational_1_2 = 1.0 / 2.0;
    const REAL_CUDA_ARRAY RK_Rational_1_2 = ConstCUDA(dblRK_Rational_1_2);

    const REAL_CUDA_ARRAY __rk_exp_0 = AddCUDA(y_n_gfsL, FusedMulAddCUDA(RK_Rational_1_2, MulCUDA(dt, k_even_gfsL), y_nplus1_running_total_gfsL));
    WriteCUDA(&y_n_gfs[i], __rk_exp_0);
  }
} // END FUNCTION rk_substep_2_gpu

/**
 * Runge-Kutta function for substep 2.
 */
static void rk_substep_2__launcher(params_struct *restrict params, REAL *restrict k_even_gfs, REAL *restrict y_n_gfs,
                                   REAL *restrict y_nplus1_running_total_gfs, const REAL dt) {
  const int Nxx_plus_2NGHOSTS0 = params->Nxx_plus_2NGHOSTS0;
  const int Nxx_plus_2NGHOSTS1 = params->Nxx_plus_2NGHOSTS1;
  const int Nxx_plus_2NGHOSTS2 = params->Nxx_plus_2NGHOSTS2;
  MAYBE_UNUSED const int Ntot = Nxx_plus_2NGHOSTS0 * Nxx_plus_2NGHOSTS1 * Nxx_plus_2NGHOSTS2 * NUM_EVOL_GFS;

  const size_t threads_in_x_dir = BHAH_THREADS_IN_X_DIR_MOL_SUBSTEP;
  const size_t threads_in_y_dir = BHAH_THREADS_IN_Y_DIR_MOL_SUBSTEP;
  const size_t threads_in_z_dir = BHAH_THREADS_IN_Z_DIR_MOL_SUBSTEP;
  dim3 threads_per_block(threads_in_x_dir, threads_in_y_dir, threads_in_z_dir);
  dim3 blocks_per_grid((Ntot + threads_in_x_dir - 1) / threads_in_x_dir, 1, 1);
  size_t sm = 0;
  size_t streamid = params->grid_idx % NUM_STREAMS;
  rk_substep_2_gpu<<<blocks_per_grid, threads_per_block, sm, streams[streamid]>>>(streamid, k_even_gfs, y_n_gfs, y_nplus1_running_total_gfs, dt);
  cudaCheckErrors(cudaKernel, "rk_substep_2_gpu failure");
} // END FUNCTION rk_substep_2__launcher

/**
 * Method of Lines (MoL) for "RK2 Heun" method: Step forward one full timestep.
 *
 */
void MoL_step_forward_in_time(commondata_struct *restrict commondata, griddata_struct *restrict griddata) {

  // C code implementation of -={ RK2 Heun }=- Method of Lines timestepping.

  // First set the initial time:
  const REAL time_start = commondata->time;
  // -={ START k1 substep }=-
  for (int grid = 0; grid < commondata->NUMGRIDS; grid++) {
    commondata->time = time_start + 0.00000000000000000e+00 * commondata->dt;
    cpyHosttoDevice_params__constant(&griddata[grid].params, griddata[grid].params.grid_idx % NUM_STREAMS);
    // Set gridfunction aliases, from griddata[].gridfuncs.
    MAYBE_UNUSED REAL *restrict y_n_gfs = griddata[grid].gridfuncs.y_n_gfs;
    MAYBE_UNUSED REAL *restrict y_nplus1_running_total_gfs = griddata[grid].gridfuncs.y_nplus1_running_total_gfs;
    MAYBE_UNUSED REAL *restrict k_odd_gfs = griddata[grid].gridfuncs.k_odd_gfs;
    MAYBE_UNUSED REAL *restrict k_even_gfs = griddata[grid].gridfuncs.k_even_gfs;
    MAYBE_UNUSED REAL *restrict auxevol_gfs = griddata[grid].gridfuncs.auxevol_gfs;
    // Set pointers to this grid's params, rfm_struct/xx, bc_struct, etc.
    MAYBE_UNUSED params_struct *restrict params = &griddata[grid].params;
    MAYBE_UNUSED REAL *restrict xx[3];
    for (int ww = 0; ww < 3; ww++)
      xx[ww] = griddata[grid].xx[ww];
    rhs_eval(commondata, params, rfmstruct, auxevol_gfs, y_n_gfs, k_odd_gfs);
    rk_substep_1__launcher(params, k_odd_gfs, y_n_gfs, y_nplus1_running_total_gfs, commondata->dt);
    if (strncmp(commondata->outer_bc_type, "extrapolation", 50) == 0)
      apply_bcs_outerextrap_and_inner(commondata, params, bcstruct, k_odd_gfs);
  }
  // -={ END k1 substep }=-

  // -={ START k2 substep }=-
  for (int grid = 0; grid < commondata->NUMGRIDS; grid++) {
    commondata->time = time_start + 1.00000000000000000e+00 * commondata->dt;
    cpyHosttoDevice_params__constant(&griddata[grid].params, griddata[grid].params.grid_idx % NUM_STREAMS);
    // Set gridfunction aliases, from griddata[].gridfuncs.
    MAYBE_UNUSED REAL *restrict y_n_gfs = griddata[grid].gridfuncs.y_n_gfs;
    MAYBE_UNUSED REAL *restrict y_nplus1_running_total_gfs = griddata[grid].gridfuncs.y_nplus1_running_total_gfs;
    MAYBE_UNUSED REAL *restrict k_odd_gfs = griddata[grid].gridfuncs.k_odd_gfs;
    MAYBE_UNUSED REAL *restrict k_even_gfs = griddata[grid].gridfuncs.k_even_gfs;
    MAYBE_UNUSED REAL *restrict auxevol_gfs = griddata[grid].gridfuncs.auxevol_gfs;
    // Set pointers to this grid's params, rfm_struct/xx, bc_struct, etc.
    MAYBE_UNUSED params_struct *restrict params = &griddata[grid].params;
    MAYBE_UNUSED REAL *restrict xx[3];
    for (int ww = 0; ww < 3; ww++)
      xx[ww] = griddata[grid].xx[ww];
    rhs_eval(commondata, params, rfmstruct, auxevol_gfs, k_odd_gfs, k_even_gfs);
    rk_substep_2__launcher(params, k_even_gfs, y_n_gfs, y_nplus1_running_total_gfs, commondata->dt);
    if (strncmp(commondata->outer_bc_type, "extrapolation", 50) == 0)
      apply_bcs_outerextrap_and_inner(commondata, params, bcstruct, y_n_gfs);
  }
  // -={ END k2 substep }=-

  // Adding dt to commondata->time many times will induce roundoff error,
  // so here we set time based on the iteration number:
  commondata->time = (REAL)(commondata->nn + 1) * commondata->dt;

  // Increment the timestep n:
  commondata->nn++;
} // END FUNCTION MoL_step_forward_in_time
