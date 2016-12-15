"""
Module containng transformers.
transformers are used to preprocess data before feeding
it into models, it is mostly used when the preprocessing
needs to fit some values from training (e.g mean and std for Standardize),
transformers allows to save these parameters and re-use them when
loading the model for the generation phase for instance.
The Transformer instances follow a scikit-learn like API.
"""
import numpy as np

EPS = 1e-10

class Standardize:

    """
    Standardize transformer.
    Estimate mean and std of each feature then
    transforms by substracting the mean and dividing
    by std.

    Parameters
    ----------

    axis: int or tuple of int
        axis or axes where to compute mean and std

    Attributes
    ----------

    mean_: numpy array
        current estimate of mean of features
    std_: numpy array
        current estimate of std of features
    n_ : int
        number of calls to partial_fit used to compute the current estimates
    """

    def __init__(self, axis=0, eps=EPS):
        self.mean_ = None
        self.std_ = None
        self.n_ = 0
        self._sum = 0
        self._sum_sqr = 0
        self.axis = axis
        self.eps = eps

    def transform(self, X):
        self._check_if_fitted()
        X = (X - self.mean_) / (self.std_ + self.eps)
        return X

    def inverse_transform(self, X):
        self._check_if_fitted()
        return (X * self.std_) + self.mean_

    def _check_if_fitted(self):
        assert self.mean_ is not None, 'the instance has not been fitted yet'
        assert self.std_ is not None, 'the instance has not been fitted yet'

    def partial_fit(self, X):
        self.n_ += len(X)
        self._sum += X.sum(axis=0)
        self._sum_sqr += (X**2).sum(axis=0)
        self.mean_ = self._sum / self.n_
        self.std_ = np.sqrt(self._sum_sqr / self.n_ - self.mean_ ** 2)

transformer = {
    'Standardize': Standardize
}

def make_transformers_pipeline(transformers):
    """
    helpers create a list of instances of Transformer.

    Parameters
    ----------

    transformers : list of dict
        each dict has two keys, `name` and `params`.
        `name` is the name of the Transformer.
        `params` are the parameters of the __init__ of the Transformer.
        available transformers :
            - 'Standardize'.

    Returns
    -------

    list of Transformer

    """
    return [transformer[t['name']](**t['params']) for t in transformers]

def fit_transformers(transformers, iter_generator):
    """
    fit a list of Transformers

    Parameters
    ----------

    transformers: list of Transformer

    iter_generator : callable
        function that returns an iterator (fresh one)

    WARNING:
        make sure that the iterators generated by the call
        are deterministic so that we don't end up each time
        with a different sample
    """
    for i, t in enumerate(transformers):
        tprev = transformers[0:i]
        for X in iter_generator():
            for tp in tprev:
                X = tp.transform(X)
            t.partial_fit(X)

def transform(iterator, transformers, col='X'):
    """
    transform an iterator with a list of Transformer

    Parameters
    ----------

    iterator: iterable of dict
        data to transform

    transformers: list of Transformer

    col: str
        modality to transform

    Yields
    ------

    transformed dict after applying the series of Transformer to
    col.
    """
    for d in iterator:
        for t in transformers:
            d[col] = t.transform(d[col])
        yield d