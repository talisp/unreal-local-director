import os as _os

_os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # 06/10: evita travamento do OpenBLAS ao carregar o numpy
