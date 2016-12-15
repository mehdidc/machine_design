"""
This module contains a list of metrics that are
common to models.
"""
import numpy as np
try:
    from itertools import izip
except  ImportError:
    izip = zip

__all__ = [
    "mean_squared_error",
    "compute_metric"
]

def mean_squared_error(y_true, y_pred):
    """mean squared error (mean over all axes except the first)"""
    axes = tuple(range(1, len(y_true.shape)))
    score = ((y_true - y_pred)**2).mean(axis=axes)
    return score

def compute_metric(get_true_and_pred, metric):
    """
    compute a metric using an iterator and true and predicted values

    Parameters
    ----------

    get_true_and_pred: callable
        should return an iterator of tuple of (true, pred) values
    metric: callable
        callable that take the true and predicted values and returns a score
        available metrics : `mean_squared_error`

    Returns
    -------

    numpy array
        the metric value for each individual element.
    """
    vals = []
    for real, pred in get_true_and_pred():
        vals.append(metric(real, pred))
    if len(vals) == 0:
        return []
    vals = np.concatenate(vals, axis=0)
    return vals
