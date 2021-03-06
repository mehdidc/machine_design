"""
This module contains some common functions used in models
"""
from __future__ import division
from __future__ import print_function

from keras.layers import Activation
from keras.layers import Dense
from keras.layers import Layer
from keras.layers import Convolution2D
from keras.layers import Convolution1D
from keras.layers import GaussianNoise
from keras.layers import LSTM
from keras.layers import GRU
from keras.layers import SimpleRNN
from keras.layers import Bidirectional
from keras.layers import Dropout
from keras.engine.training import Model
from keras import optimizers

from .objectives import objectives
from .layers import layers
from .layers import CategoricalNoise
from .layers import WordDropout
from .layers import Normalize
from .layers import SaltAndPepper

custom_objects = {}
custom_objects.update(objectives)
custom_objects.update(layers)


def activation_function(name, layers=layers):
    """
    gives an activation function based on its name.

    Parameters
    ----------

    name : str or dict

        - if it is str, assumes it is a keras activation function.
        - if it is a dict, search in layers of the layers module.
          it should have two keys, 'name' and 'params'.
    """
    if isinstance(name, dict):
        act = name
        name, params = act['name'], act['params']
        if name in layers:
            return layers[name](**params)
        else:
            raise ValueError('Unknown activation function : {}'.format(name))
    else:
        return Activation(name)


def noise(x, name, params):
    """
    noise application helper.

    name : 'gaussian' / 'zero_masking' / 'categorical' / 'word_dropout' / 'none'
        type of noise
    params: dict
        if name is 'gaussian':
            'std' : standard deviation of gaussian noise
        if name is 'zero_masking':
            'proba': probability of zeroing the units
        if name is 'salt_and_pepper':
            'proba': probability of zeroing the units
    """
    if name == 'gaussian':
        std = params['std']
        return GaussianNoise(std)(x)
    elif name == 'zero_masking':
        proba = params['proba']
        x = Dropout(proba)(x)
        x = Normalize(bias=0, scale=proba)(x)
        return x
    elif name == 'salt_and_pepper':
        proba = params['proba']
        return SaltAndPepper(proba)(x)
    elif name == 'categorical':
        return CategoricalNoise(**params)(x)
    elif name == 'word_dropout':
        return WordDropout(**params)(x)
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
        (should be at least the same size than nb_hidden_units).
        the first len(nb_hidden_units) activations are applied after each layer.
        the rest is applied after the last layer, one after the other.

    Returns
    -------

    keras layer
    """
    assert len(activations) >= len(nb_hidden_units)
    for nb_hidden, act in zip(nb_hidden_units, activations):
        x = Dense(nb_hidden, kernel_initializer=init)(x)
        x = activation_function(act)(x)
    rest = activations[len(nb_hidden_units):]
    for act in rest:
        x = activation_function(act)(x)
    return x


def conv2d_layers(x, nb_filters, filter_sizes, activations,
                  init='glorot_uniform', border_mode='valid',
                  stride=1, conv_layer=Convolution2D):
    """
    Apply a stack of 2D convolutions to a layer `x` and return
    the resulting layer
    """
    layers = conv2d_layers_all(
        x, 
        nb_filters, 
        filter_sizes, 
        activations, 
        init=init, 
        border_mode=border_mode, 
        stride=stride, 
        conv_layer=conv_layer
    )
    return layers[-1]


def conv2d_layers_all(x, nb_filters, filter_sizes, activations,
                     init='glorot_uniform', border_mode='valid',
                     stride=1, conv_layer=Convolution2D):
    """
    Apply a stack of 2D convolutions to a layer `x` and return all
    the intermediate layers

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

    list keras layer

    """
    assert len(nb_filters) == len(filter_sizes) == len(activations)
    layers = []
    for nb_filter, filter_size, act in zip(nb_filters, filter_sizes, activations):
        x = conv_layer(nb_filter, (filter_size, filter_size), kernel_initializer=init,
                       padding=border_mode, strides=(stride, stride))(x)
        x = activation_function(act)(x)
        layers.append(x)
    return layers


 

def conv1d_layers(x, nb_filters, filter_sizes, activations,
                  init='glorot_uniform', border_mode='valid',
                  conv_layer=Convolution1D):
    """
    Apply a stack of 1D convolutions to a layer `x`

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
    conv_layer : keras layer class
        keras layer to use from convolution

    Returns
    -------

    keras layer
    """
    assert len(nb_filters) == len(filter_sizes) == len(activations)
    for nb_filter, filter_size, act in zip(nb_filters, filter_sizes, activations):
        x = conv_layer(nb_filter, filter_size, init=init, border_mode=border_mode)(x)
        x = activation_function(act)(x)
    return x


def _bidirectional(rnn_class):
    def f(*args, **kwargs):
        return Bidirectional(rnn_class(*args, **kwargs))
    return f

rnn_classes = {
    'GRU': GRU,
    'LSTM': LSTM,
    'RNN': SimpleRNN,
    'BidirectionalLSTM': _bidirectional(LSTM),
    'BidirectionalGRU': _bidirectional(GRU),
    'BidirectionalRNN': _bidirectional(SimpleRNN)
}


def rnn_stack(x, nb_hidden_units, rnn_type='GRU', return_sequences=True, stateful=False, dropout=None):
    rnn_class = rnn_classes[rnn_type]
    for i, nb_units in enumerate(nb_hidden_units):
        r = True if i < len(nb_hidden_units) - 1 else return_sequences
        pr = dropout[i] if dropout else 0
        x = rnn_class(nb_units, return_sequences=r, stateful=stateful,
                      dropout_U=pr, dropout_W=pr)(x)
    return x


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
    optimizer = _get_optimizer(algo_name)
    optimizer = optimizer(**algo_params)
    return optimizer


def _get_optimizer(name):
    """Get a keras optimizer class from its name"""
    if hasattr(optimizers, name):
        return getattr(optimizers, name)
    else:
        raise Exception('unknown optimizer : {}'.format(name))


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
        raise WrongModelFamilyException(
            "expected family to be '{}', got {}".format(expected, family))


def show_model_info(model, print_func=print):
    print_func('Input shape : {}'.format(model.input_shape))
    print_func('Output shape : {}'.format(model.output_shape))
    print_func('Number of parameters : {}'.format(model.count_params()))
    model.summary()


def _get_layers(model):
    for layer in model.layers:
        if isinstance(layer, Model):
            for l in _get_layers(layer):
                yield l
        elif isinstance(layer, Layer):
            yield layer


def check_model_shape_or_exception(model, shape):
    """
    check if `model` output shape is `shape`. if it is not raises a ValueError exception.
    `shape` does not have the first axis (example axis), it is from the second axis
    till the end, e.g for an image tensor it should be (3, 100, 100).

    Parameters
    ----------
    """
    if model.output_shape[1:] != shape:
        msg = """Wrong output shape of the model, expected : {}, got : {}.
                 Please fix the parameters""".format(shape, model.output_shape[1:])
        raise ValueError(msg)


def callback_trigger(callbacks, event_name, *args, **kwargs):
    """

    call an event on a list of callbacks.
    the event_name correspond to a method of the class Callback.
    Available are :
        - on_train_begin
        - on_train_end
        - on_epoch_begin
        - on_epoch_end
        - on_batch_begin
        - on_batch_end

    Parameters
    ----------

    callbacks : list of Callback
    event_name : str
        event to call
    """
    for cb in callbacks:
        getattr(cb, event_name)(*args, **kwargs)


def get_layers(model):
    for lay in model.layers:
        if isinstance(lay, Model):
            for lay_ in get_layers(lay):
                yield lay_
        else:
            yield lay
