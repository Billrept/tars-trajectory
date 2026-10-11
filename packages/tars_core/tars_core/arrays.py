import io,zipfile
import numpy as np
from .ephemeris import EphemerisSnapshot

MAX_BYTES=64*1024*1024

def decode_arrays(raw):
    if len(raw)>4*1024*1024:raise ValueError('Compressed body data exceeds limit')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if len(z.infolist())!=3 or set(z.namelist())!={'epochs.npy','positions.npy','velocities.npy'} or sum(x.file_size for x in z.infolist())>MAX_BYTES:
                raise ValueError('Invalid or oversized numerical archive')
        with np.load(io.BytesIO(raw),allow_pickle=False) as z:
            arrays={key:z[key] for key in ('epochs','positions','velocities')}
        if any(x.dtype!=np.dtype('float64') for x in arrays.values()):raise ValueError('Expected float64 arrays')
        EphemerisSnapshot('validation',{399:arrays})
        return arrays
    except (zipfile.BadZipFile,KeyError,OSError) as e:raise ValueError('Invalid numerical archive') from e

