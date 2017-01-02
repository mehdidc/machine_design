"""
This module contains some common functions used in models
"""
from __future__ import division
import os
import numpy as np
import csv

from keras.layers import Activation
from keras.layers import Dense
from keras.layers import Layer
from keras.layers import Convolution2D
from keras.layers import GaussianNoise
from keras.layers import LeakyReLU
from keras import optimizers
import keras.backend as K

from .objectives import custom_objectives

__all__ = [
    "ksparse",
    "winner_take_all_spatial",
    "custom_layers",
    "activation_function",
    "fully_connected_layers",
    "get_optimizer",
    "build_optimizer",
    "object_to_dict",
    "mkdir_path",
    "minibatcher",
    "iterate_minibatches",
    "WrongModelFamilyException",
    "check_family_or_exception"
]


class ksparse(Layer):
    #TODO make it compatible with tensorflow (only works with theano)
    """
    For each example, sort activations, then zerout a proportion of zero_ratio from the smallest activations,
    that rest (1 - zero_ratio) is kept as it is.
    Works inly for fully connected layers.
    Corresponds to k-sparse autoencoders in [1].

    References
    ----------

    [1] Makhzani, A., & Frey, B. (2013). k-Sparse Autoencoders. arXiv preprint arXiv:1312.5663.

    """
    def __init__(self, zero_ratio=0,  **kwargs):
        super(ksparse, self).__init__(**kwargs)
        self.zero_ratio = zero_ratio

    def call(self, X, mask=None):
        import theano.tensor as T
        idx = T.cast(self.zero_ratio * T.cast(X.shape[1], 'float32'), 'int32')
        theta = X[T.arange(X.shape[0]), T.argsort(X, axis=1)[:, idx]]
        mask = X >= theta[:, None]
        return X * mask

    def get_config(self):
        config = {'zero_ratio': self.zero_ratio}
        base_config = super(ksparse, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))

class winner_take_all_spatial(Layer):
    #TODO make it compatible with tensorflow (only works with theano)

    """
    Winner take all spatial sparsity defined in [1].
    it takes a convolutional layer, then for each feature map,
    keep only nb_active positions with biggets value
    and zero-out the rest. nb_active=1 corresponds to [1],
    but it can be bigger.
    assumes input of shape (nb_examples, nb_features_maps, h, w).

    Parameters
    ----------

    nb_active : int
        number of active positions in each feature map

    References
    ----------
    [1] Makhzani, A., & Frey, B. J. (2015). Winner-take-all autoencoders.
    In Advances in Neural Information Processing Systems (pp. 2791-2799).

    """
    def __init__(self, nb_active=1, **kwargs):
        super(winner_take_all_spatial, self).__init__(**kwargs)
        self.nb_active = nb_active

    def call(self, X, mask=None):
        if self.nb_active == 0:
            return X*0
        elif self.nb_active == 1:
            return _winner_take_all_spatial_one_active(X)
        else:
            import theano.tensor as T
            shape = X.shape
            X_ = X.reshape((X.shape[0] * X.shape[1], X.shape[2] * X.shape[3]))
            idx = T.argsort(X_, axis=1)[:, X_.shape[1] - T.minimum(self.nb_active, X_.shape[1])]
            val = X_[T.arange(X_.shape[0]), idx]
            mask = X_ >= val.dimshuffle(0, 'x')
            X_ = X_ * mask
            X_ = X_.reshape(shape)
            return X_

    def get_config(self):
        config = {'nb_active': self.nb_active}
        base_config = super(winner_take_all_spatial, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))

def _winner_take_all_spatial_one_active(X):
    mask = (_equals(X, K.max(X, axis=(2, 3), keepdims=True))) * 1
    return X * mask

class winner_take_all_channel(Layer):
    """
    divide each channel into a grid of sizes stride x stride.
    for each grid, across all channels, only one value (the max value) will be active.
    assumes input of shape (nb_examples, nb_features_maps, h, w).

    Parameters
    ----------

    stride : int
        size of the stride

    """
    def __init__(self, stride=1, **kwargs):
        super(winner_take_all_channel, self).__init__(**kwargs)
        self.stride = stride

    def call(self, X, mask=None):
        B, F = X.shape[0:2]
        w, h = X.shape[2:]
        X_ = X.reshape((B, F, w // self.stride, self.stride, h // self.stride, self.stride))
        mask = _equals(X_, X_.max(axis=(1, 3, 5), keepdims=True)) * 1
        mask = mask.reshape(X.shape)
        return X * mask

    def get_config(self):
        config = {'stride': self.stride}
        base_config = super(winner_take_all_channel, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))

def _equals(x, y, eps=1e-8):
    return K.abs(x - y) <= eps

class axis_softmax(Layer):
    """
    softmax on a given axis
    keras default softmax only works for matrices and applies to axis=1.
    this works for any tensor and any axis.

    Parameters
    ----------

    axis: int(default=1)
        axis where to do softmax
    """
    def __init__(self, axis=1, **kwargs):
        super(axis_softmax, self).__init__(**kwargs)
        self.axis = axis

    def call(self, X, mask=None):
        e_X = K.exp(X - X.max(axis=self.axis, keepdims=True))
        e_X = e_X / e_X.sum(axis=self.axis, keepdims=True)
        return e_X

    def get_config(self):
        config = {'axis': self.axis}
        base_config = super(axis_softmax, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))

class UpConv2D(Convolution2D):
    """
    This is  a simple up convolution layer that rescales the dimension of a
    convolutional layer.
    It only works with border_mode='same', if it is not the case, an
    exception will be thrown.
    """
    def get_output_shape_for(self, input_shape):
        assert self.border_mode == 'same'
        N, c, h, w = input_shape
        h = h * self.subsample[0]
        w = w * self.subsample[1]
        input_shape = N, self.nb_filter, h, w
        return input_shape

    def call(self, x, mask=None):
        assert self.border_mode == 'same'

        # inspired by : <http://distill.pub/2016/deconv-checkerboard/>
        # Upsample by just copying pixel values in grids of size subsamplexsubsample
        sh, sw = self.subsample
        assert sh == sw
        s = sh
        # don't do anything if there is any subsampling
        if s > 1:
            #TODO make this comptabile with tensorflow
            import theano.tensor as T
            shape = x.shape
            x = x.reshape((x.shape[0], x.shape[1], x.shape[2], 1, x.shape[3], 1))
            x = T.ones((shape[0], shape[1], shape[2], s, shape[3], s)) * x
            x = x.reshape((shape[0], shape[1], shape[2] * s, shape[3] * s))
        # equivalent to keras code except strides=(1, 1) instead
        # of being equal to self.subsample
        output = K.conv2d(x, self.W, strides=(1, 1),
                          border_mode=self.border_mode,
                          dim_ordering=self.dim_ordering,
                          filter_shape=self.W_shape)
        if self.bias:
            if self.dim_ordering == 'th':
                output += K.reshape(self.b, (1, self.nb_filter, 1, 1))
            elif self.dim_ordering == 'tf':
                output += K.reshape(self.b, (1, 1, 1, self.nb_filter))
            else:
                raise Exception('Invalid dim_ordering: ' + self.dim_ordering)
        output = self.activation(output)
        return output

custom_layers = {
    'ksparse': ksparse,
    'winner_take_all_spatial': winner_take_all_spatial,
    'winner_take_all_channel': winner_take_all_channel,
    'axis_softmax': axis_softmax,
    'UpConv2D': UpConv2D,
    'leaky_relu': LeakyReLU
}

custom_objects = {}
custom_objects.update(custom_objectives)
custom_objects.update(custom_layers)

def activation_function(name):
    if isinstance(name, dict):
        act = name
        name, params = act['name'], act['params']
        if name in custom_layers:
            return custom_layers[name](**params)
        else:
            raise ValueError('Unknown activation function : {}'.format(name))
    else:
        return Activation(name)

def noise(x, name, params):
    if name == 'gaussian':
        std = params['std']
        return GaussianNoise(std)(x)
    elif name == 'none':
        return x
    else:
        raise ValueError('Unknown noise function')

def fully_connected_layers(x, nb_hidden_units, activations, init='glorot_uniform'):
    """
    Apply a stack of fully connected layers to a layer `x`

    Parameters
    ----------

    x : keras layer
    nb_hidden_units : list of int
        number of hidden units
    activations : str
        list of activation functions for each layer
        (should be the same size than nb_hidden_units)

    Returns
    -------

    keras layer
    """
    assert len(activations) == len(nb_hidden_units)
    for nb_hidden, act in zip(nb_hidden_units, activations):
        x = Dense(nb_hidden, init=init)(x)
        x = activation_function(act)(x)
    return x

def conv2d_layers(x, nb_filters, filter_sizes, activations,
                  init='glorot_uniform', border_mode='valid',
                  stride=1, conv_layer=Convolution2D):
    """
    Apply a stack of 2D convolutions to a layer `x`

    Parameters
    ----------

    x : keras layer
    nb_filters : list of int
        nb of filters/feature_maps per layer
    filter_sizes : list of int
        size of (square) filters per layer
    activations : str
        list of activation functions for each layer
        (should be the same size than nb_hidden_units)
    init : str
        init method used in all layers
    border_mode : str
        padding type to use in all layers
    stride : int
        stride to use
    conv_layer : keras layer class
        keras layer to use from convolution

    Returns
    -------

    keras layer
    """
    assert len(nb_filters) == len(filter_sizes) == len(activations)
    for nb_filter, filter_size, act in zip(nb_filters, filter_sizes, activations):
        x = conv_layer(nb_filter, filter_size, filter_size, init=init, border_mode=border_mode, subsample=(stride, stride))(x)
        x = activation_function(act)(x)
    return x

def get_optimizer(name):
    """Get a keras optimizer class from its name"""
    if hasattr(optimizers, name):
        return getattr(optimizers, name)
    else:
        raise Exception('unknown optimizer : {}'.format(name))

def build_optimizer(algo_name, algo_params):
    """
    build a keras optimizer instance from its name and params

    Parameters
    ----------
        algo_name: str
            name of the optimizer
        algo_params: dict
            parameters of the optimizer
    """
    optimizer = get_optimizer(algo_name)
    optimizer = optimizer(**algo_params)
    return optimizer

def object_to_dict(obj):
    """return the attributes of an object"""
    return obj.__dict__

def mkdir_path(path):
    """
    Create folder in `path` silently: if it exists, ignore, if not
    create all necessary folders reaching `path`
    """
    if not os.access(path, os.F_OK):
        os.makedirs(path)


def minibatcher(func, batch_size=1000):
  """
  Decorator to apply a function minibatch wise to avoid memory
  problems.

  Paramters
  ---------
  func : a function that takes an input and returns an output
  batch_size : int
    size of each minibatch

  iterate through all the minibatches, call func, get the results,
  then concatenate all the results.
  """
  def f(X):
      results = []
      for sl in iterate_minibatches(len(X), batch_size):
          results.append(func(X[sl]))
      if len(results) == 0:
          return []
      else:
          return np.concatenate(results, axis=0)
  return f

def iterate_minibatches(nb_inputs, batch_size):
  """
  Get slices pointing to indices of example forming minibatches

  Paramaters
  ----------
  nb_inputs : int
    size of the data
  batch_size : int
    minibatch size

  Yields
  ------

  slice
  """
  for start_idx in range(0, nb_inputs, batch_size):
      end_idx = min(start_idx + batch_size, nb_inputs)
      excerpt = slice(start_idx, end_idx)
      yield excerpt

class WrongModelFamilyException(ValueError):
    """
    raised when the model family is not the expected one
    model families are kinds of models different enough in
    their training pipeline that they need to be separated:
    e.g GAN and autoencoders are distinct families.
    """
    pass

def check_family_or_exception(family, expected):
    """if family is not equal to expected, raise WrongModelFamilyException"""
    if family != expected:
        raise WrongModelFamilyException("expected family to be '{}', got {}".format(expected, family))

def show_model_info(model, print_func=print):
    print_func('Input shape : {}'.format(model.input_shape))
    print_func('Output shape : {}'.format(model.output_shape))
    print_func('Number of parameters : {}'.format(model.count_params()))
    nb = sum(1 for layer in model.layers if hasattr(layer, 'W'))
    nb_W_params = sum(np.prod(layer.W.get_value().shape) for layer in model.layers if hasattr(layer, 'W'))
    print_func('Number of weight parameters : {}'.format(nb_W_params))
    print_func('Number of learnable layers : {}'.format(nb))

def write_csv(iterable, filename):
    """
    write a list of dicts into a csv file
    (like pandas.to_csv(...) but I didnt want to add that dependency
     just for that)

    Parameters
    ----------

    iterable : iterable of dict
        this will constitute the rows of the csv file.
        the header will be the keys of the dicts.
    filename : str
        filename where to write the content
    """
    with open(filename, 'w') as f:
        writer = csv.DictWriter(f, fieldnames=iterable[0].keys())
        writer.writeheader()
        writer.writerows(iterable)
