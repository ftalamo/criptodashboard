import numpy as np
# ==============================
#  LIMPIAR TIPOS DE NUMPY
# ==============================
def clean_numpy(obj):
    if isinstance(obj, np.generic):
        return obj.item()
    elif isinstance(obj, dict):
        return {k: clean_numpy(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_numpy(i) for i in obj]
    else:
        return obj
