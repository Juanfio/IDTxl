from pkg_resources import resource_filename
import numpy as np
from . import idtxl_exceptions as ex
try:
    import pyopencl as cl
except ImportError:  
    ex.opencl_missing('PyOpenCl is not available on this system. To use '
                      'OpenCL-powered CMI estimation install it from '
                      'https://pypi.python.org/pypi/pyopencl')

VERBOSE = False

def knn_search(pointset, n_dim, knn_k, theiler_t, n_chunks=1, gpuid=0):
    """Interface with OpenCL knn search from Python/IDTxl.
    
    Function checks input for correct dimensionality and transposes point sets
    if necessary. Function also checks the maximum available memory on the GPU
    device and splits chunks over multiple calls to the GPU (runs).
    """

    # check for a data layout in memory as expected by the low level functions
    # ndim * [n_points * n_chunks]
    if n_dim !=  pointset.shape[0]:
        assert n_dim == pointset.shape[1], "given dimension does not match data"
        pointset = pointset.transpose().copy()
        if VERBOSE:
            print('search GPU: fixed shape of input data')
    if pointset.flags['C_CONTIGUOUS'] != True:
        pointset = np.ascontiguousarray(pointset)
        if VERBOSE:
            print('search GPU: fixed memory layout of input data')

    # Allocate memory for GPU search output.
    indexes = np.zeros((knn_k, pointset.shape[1]), dtype=np.int32)
    distances = np.zeros((knn_k, pointset.shape[1]), dtype=np.float32)

    # Calculate the maximum number of chunks that fit into the GPU's global memory given the
    # current chunk size. Calculate the number of necessary runs (calls to the GPU) given the
    # max. number of chunks that fit onto the GPU and the actual number of chunks.
    max_chunks_per_run = _get_max_chunks_per_run(gpuid, n_chunks, pointset, distances, indexes)
    max_chunks_per_run = min(max_chunks_per_run, n_chunks)  # check if chunks fit into GPU in one run
    n_runs = np.ceil(n_chunks / max_chunks_per_run).astype(int)
    
    chunksize = int(pointset.shape[1] / n_chunks)
    i_1 = 0
    i_2 = max_chunks_per_run * chunksize
    pointdim = pointset.shape[0]
    n_points = pointset[:, i_1:i_2].shape[1]
    for r in range(n_runs):
        # print('run: {0}, index 1: {1}, index 2: {2}'.format(r, i_1, i_2))
        # print('no. points: {0}, no. chunks: {1}, pointset shape: {2}'.format(n_points, n_chunks, pointset[:, i_1:i_2].shape))
        success = clFindKnn(indexes[:, i_1:i_2], distances[:, i_1:i_2],
                            pointset[:, i_1:i_2].astype('float32'),
                            pointset[:, i_1:i_2].astype('float32'), int(knn_k), int(theiler_t),
                            int(n_chunks), int(pointdim), int(n_points), int(gpuid))
        if not success:
            print("Error in OpenCL knn search!")
            return 1
        i_1 = i_2
        i_2 = min(i_2 + max_chunks_per_run * chunksize, pointset.shape[1])

    return (indexes, distances)

def range_search(pointset, n_dim, radius, theiler_t, n_chunks=1, gpuid=0):
    """Interface with OpenCL range search from Python/IDTxl.
    
    Function checks input for correct dimensionality and transposes point sets
    if necessary. Function also checks the maximum available memory on the GPU
    device and splits chunks over multiple calls to the GPU (runs).
    """

    # check for a data layout in memory as expected by the low level functions
    # ndim * [n_points * n_chunks]
    if n_dim !=  pointset.shape[0]:
        assert n_dim == pointset.shape[1], "given dimension does not match data axis"
        pointset = pointset.transpose().copy()
        if VERBOSE:
            print('search GPU: fixed shape input data')
    if pointset.flags['C_CONTIGUOUS'] != True:
        pointset = np.ascontiguousarray(pointset)
        if VERBOSE:
            print('search GPU: fixed memory layout of input data')
    
    # Allocate memory for GPU search output
    pointcount = np.zeros((pointset.shape[1]), dtype=np.int32)

    # Calculate the maximum number of chunks that fit into the GPU's global memory given the
    # current chunk size. Calculate the number of necessary runs (calls to the GPU) given the
    # max. number of chunks that fit onto the GPU and the actual number of chunks.
    max_chunks_per_run = _get_max_chunks_per_run(gpuid, n_chunks, pointset, pointcount, radius)
    max_chunks_per_run = min(max_chunks_per_run, n_chunks)  # check if chunks fit into GPU in one run
    n_runs = np.ceil(n_chunks / max_chunks_per_run).astype(int)
    
    chunksize = int(pointset.shape[1] / n_chunks)
    i_1 = 0
    i_2 = max_chunks_per_run * chunksize
    pointdim = pointset.shape[0]
    n_points = pointset[:, i_1:i_2].shape[1]
    for r in range(n_runs):
        success = clFindRSAll(pointcount[i_1:i_2], pointset[:, i_1:i_2].astype('float32'),
                              pointset[:, i_1:i_2].astype('float32'), radius[i_1:i_2], theiler_t,
                              n_chunks, pointdim, n_points, gpuid)
        if not success:
            print("Error in OpenCL knn search!")
            return 1
        i_1 = i_2
        i_2 = min(i_2 + max_chunks_per_run * chunksize, pointset.shape[1])

    return pointcount

def clFindKnn(h_bf_indexes, h_bf_distances, h_pointset, h_query, kth, thelier,
              nchunks, pointdim, signallength, gpuid):

    triallength = int(signallength / nchunks)
#    print 'Values:', pointdim, triallength, signallength, kth, thelier

    '''for platform in cl.get_platforms():
        for device in platform.get_devices():
            print("===============================================================")
            print("Platform name:", platform.name)
            print("Platform profile:", platform.profile)
            print("Platform vendor:", platform.vendor)
            print("Platform version:", platform.version)
            print("---------------------------------------------------------------")
            print("Device name:", device.name)
            print("Device type:", cl.device_type.to_string(device.type))
            print("Device memory: ", device.global_mem_size//1024//1024, 'MB')
            print("Device max clock speed:", device.max_clock_frequency, 'MHz')
            print("Device compute units:", device.max_compute_units)
            print("Device max work group size:", device.max_work_group_size)
            print("Device max work item sizes:", device.max_work_item_sizes)'''

    # Set up OpenCL
    my_gpu_devices, context, queue = _get_device(gpuid)

    # Check memory resources.
    usedmem =int( (h_query.nbytes + h_pointset.nbytes + h_bf_distances.nbytes + h_bf_indexes.nbytes)//1024//1024)
    totalmem = int(my_gpu_devices[gpuid].global_mem_size//1024//1024)

    if (totalmem*0.90) < usedmem:
        print(("WARNING:", usedmem, "Mb used out of", totalmem,
               "Mb. The GPU could run out of memory."))


    # Create OpenCL buffers
    d_bf_query = cl.Buffer(context, cl.mem_flags.READ_ONLY | cl.mem_flags.COPY_HOST_PTR, hostbuf=h_query)
    d_bf_pointset = cl.Buffer(context, cl.mem_flags.READ_ONLY | cl.mem_flags.COPY_HOST_PTR, hostbuf=h_pointset)
    d_bf_distances = cl.Buffer(context, cl.mem_flags.READ_WRITE, h_bf_distances.nbytes)
    d_bf_indexes = cl.Buffer(context, cl.mem_flags.READ_WRITE, h_bf_indexes.nbytes)

    # Kernel Launch
    kernelLocation = resource_filename(__name__, 'gpuKnnBF_kernel.cl')
    kernelsource = open(kernelLocation).read()
    program = cl.Program(context, kernelsource).build()
    kernelKNNshared = program.kernelKNNshared
    kernelKNNshared.set_scalar_arg_dtypes([None, None, None, None, np.int32, np.int32, np.int32, np.int32, np.int32, None, None])

    #Size of workitems and NDRange
    if signallength/nchunks < my_gpu_devices[gpuid].max_work_group_size:
        workitems_x = 8
    elif my_gpu_devices[gpuid].max_work_group_size < 256:
        workitems_x = my_gpu_devices[gpuid].max_work_group_size
    else:
        workitems_x = 256

    if signallength%workitems_x != 0:
        temp = int(round(((signallength)/workitems_x), 0) + 1)
    else:
        temp = int(signallength/workitems_x)

    NDRange_x = workitems_x * temp

    #Local memory for distances and indexes
    localmem = (np.dtype(np.float32).itemsize*kth*workitems_x + np.dtype(np.int32).itemsize*kth*workitems_x)/1024
    if localmem > my_gpu_devices[gpuid].local_mem_size/1024:
        print(( "Localmem alocation will fail.", my_gpu_devices[gpuid].local_mem_size/1024, "kb available, and it needs", localmem, "kb."))
    localmem1 = cl.LocalMemory(np.dtype(np.float32).itemsize*kth*workitems_x)
    localmem2 = cl.LocalMemory(np.dtype(np.int32).itemsize*kth*workitems_x)

    kernelKNNshared(queue, (NDRange_x,), (workitems_x,), d_bf_query, d_bf_pointset, d_bf_indexes, d_bf_distances, pointdim, triallength, signallength,kth,thelier, localmem1, localmem2)

    queue.finish()

    # Download results
    cl.enqueue_copy(queue, h_bf_distances, d_bf_distances)
    cl.enqueue_copy(queue, h_bf_indexes, d_bf_indexes)


    # Free buffers
    d_bf_distances.release()
    d_bf_indexes.release()
    d_bf_query.release()
    d_bf_pointset.release()

    return 1

'''
 * Range search being radius a vector of length number points in queryset/pointset
'''

def clFindRSAll(h_bf_npointsrange, h_pointset, h_query, h_vecradius, thelier,
                nchunks, pointdim, signallength, gpuid):

    triallength = int(signallength / nchunks)
    #print 'Values:', pointdim, triallength, signallength, kth, thelier

    '''for platform in cl.get_platforms():
        for device in platform.get_devices():
            print("===============================================================")
            print("Platform name:", platform.name)
            print("Platform profile:", platform.profile)
            print("Platform vendor:", platform.vendor)
            print("Platform version:", platform.version)
            print("---------------------------------------------------------------")
            print("Device name:", device.name)
            print("Device type:", cl.device_type.to_string(device.type))
            print("Device memory: ", device.global_mem_size//1024//1024, 'MB')
            print("Device max clock speed:", device.max_clock_frequency, 'MHz')
            print("Device compute units:", device.max_compute_units)
            print("Device max work group size:", device.max_work_group_size)
            print("Device max work item sizes:", device.max_work_item_sizes)'''

    # Set up OpenCL
    my_gpu_devices, context, queue = _get_device(gpuid)

    #Check memory resources.
    usedmem = int((h_query.nbytes + h_pointset.nbytes + h_vecradius.nbytes + h_bf_npointsrange.nbytes)//1024//1024)
    totalmem = int(my_gpu_devices[gpuid].global_mem_size//1024//1024)

    if (totalmem*0.90) < usedmem:
        print(("WARNING:", usedmem, "Mb used from a total of", totalmem, "Mb. GPU could get without memory"))

    # Create OpenCL buffers
    d_bf_query = cl.Buffer(context, cl.mem_flags.READ_ONLY | cl.mem_flags.COPY_HOST_PTR, hostbuf=h_query)
    d_bf_pointset = cl.Buffer(context, cl.mem_flags.READ_ONLY | cl.mem_flags.COPY_HOST_PTR, hostbuf=h_pointset)
    d_bf_vecradius = cl.Buffer(context, cl.mem_flags.READ_ONLY | cl.mem_flags.COPY_HOST_PTR, hostbuf=h_vecradius)
    d_bf_npointsrange = cl.Buffer(context, cl.mem_flags.READ_WRITE, h_bf_npointsrange.nbytes)

    # Kernel Launch
    kernelLocation = resource_filename(__name__, 'gpuKnnBF_kernel.cl')
    kernelsource = open(kernelLocation).read()
    program = cl.Program(context, kernelsource).build()
    kernelBFRSAllshared = program.kernelBFRSAllshared
    kernelBFRSAllshared.set_scalar_arg_dtypes([None, None, None, None, np.int32, np.int32, np.int32, np.int32, None])

    #Size of workitems and NDRange
    if signallength/nchunks < my_gpu_devices[gpuid].max_work_group_size:
        workitems_x = 8
    elif my_gpu_devices[gpuid].max_work_group_size < 256:
        workitems_x = my_gpu_devices[gpuid].max_work_group_size
    else:
        workitems_x = 256

    if signallength%workitems_x != 0:
        temp = int(round(((signallength)/workitems_x), 0) + 1)
    else:
        temp = int(signallength/workitems_x)

    NDRange_x = workitems_x * temp

    #Local memory for rangesearch. Actually not used, better results with private memory
    localmem = cl.LocalMemory(np.dtype(np.int32).itemsize*workitems_x)

    kernelBFRSAllshared(queue, (NDRange_x,), (workitems_x,), d_bf_query, d_bf_pointset, d_bf_vecradius, d_bf_npointsrange, pointdim, triallength, signallength, thelier, localmem)

    queue.finish()

    # Download results
    cl.enqueue_copy(queue, h_bf_npointsrange, d_bf_npointsrange)

    # Free buffers
    d_bf_npointsrange.release()
    d_bf_vecradius.release()
    d_bf_query.release()
    d_bf_pointset.release()

    return 1

def find_nonempty(a_list):
    for idx in range(0,len(a_list)):
        if a_list[idx].get_devices(device_type= cl.device_type.GPU) != []:
            break
        else:
            if VERBOSE:
                print('found empty platform')

    if a_list[idx] == []:
        print('all platforms empty')
    else:
        return idx

def _get_max_chunks_per_run(gpuid, n_chunks, pointset, ar1, ar2): # TODO make this more generic, i.e., a variable number of arrays as input
    """Calculate number of chunks per GPU run based on the global memory and problem size.

    Checks the global memory on the requested GPU device and the problem size, which is defined by
    twice the size of the pointset (used as reference and query set by the GPU, i.e., it is passed
    twice to the device), and two additional arrays (pointcount and radii for range search, and
    indices and distances for knn search).

    The function calculates the maximum number of chunks that can be searched on the GPU in parallel
    and returns this number.

    Args:
        gpuid : int
            number of the GPU device
        n_chunks : int
            number of chunks in the input data
        pointset : numpy array
            search space and query points, axes are assumed to represent [variable dim x points]
        ar1 : numpy array
            first auxiliary array used for range or knn search
        ar2 : numpy array
            second auxiliary array used for range or knn search

    Returns:
        int
            maximum number of chunks that fits onto the GPU in one run

    Note:
        The function assumes transposed input arrays, i.e., the orientation of the point sets
        differs from the main code. This is due to the implementation of the low-level OpenCl
        functions and may change in the future. TODO
    """
    # Check memory resources, we check that the required memory per run does not exceed
    # (total_mem * 0.90), this is also used inside the PyOpenCl code from Mario and colleagues.
    my_gpu_devices = _get_device(gpuid)[0]
    chunksize = int(pointset.shape[1] / n_chunks)
    total_mem = int(my_gpu_devices[gpuid].global_mem_size / 1024 / 1024)
    if len(ar2.shape) == 2:
        mem_per_chunk = int(np.ceil((2 * pointset[:, :chunksize].nbytes + ar1[:, :chunksize].nbytes +
                                    ar2[:,:chunksize].nbytes) / 1024 / 1024))
    else:  # when testing this for range searches, the 2nd array is only one-dimensional TODO make this more elegant
        mem_per_chunk = int(np.ceil((2 * pointset[:, :chunksize].nbytes + ar1[:chunksize].nbytes +
                                    ar2[:chunksize].nbytes) / 1024 / 1024))
    if VERBOSE:
	    print('no. chunks: {0}, chunksize: {1} points, device global memory: {2} MB, memory per chunk: {3} MB'.format(
		                                                   n_chunks, chunksize, total_mem, mem_per_chunk))
    if mem_per_chunk > (total_mem * 0.90):
        raise RuntimeError(('Size of single chunk exceeds GPU global memory. '
                            'Reduce Problem size.'))
    else:
        chunks_per_run = np.floor(total_mem * 0.90 / mem_per_chunk).astype(int)

    if VERBOSE:
        print('max. allowed no. chunks per run is {0}.'.format(chunks_per_run))
    return chunks_per_run

def _get_device(gpuid):
    """Return GPU devices, context, and queue."""
    platform = cl.get_platforms()
    platf_idx = find_nonempty(platform)
    my_gpu_devices = platform[platf_idx].get_devices(device_type=cl.device_type.GPU)
    context = cl.Context(devices=my_gpu_devices)
    queue = cl.CommandQueue(context, my_gpu_devices[gpuid])
    if VERBOSE:
        print(("Selected Device: ", my_gpu_devices[gpuid].name))
    return my_gpu_devices, context, queue
