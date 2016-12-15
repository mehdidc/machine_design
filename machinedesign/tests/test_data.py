import numpy as np
from machinedesign.data import get_nb_samples
from machinedesign.data import get_shapes
from machinedesign.data import get_nb_minibatches
from machinedesign.data import BatchIterator

toy_pipeline = [
    {"name": "toy", "params": {"nb": 50, "w": 8, "h": 8, "pw": 2, "ph": 2, "nb_patches": 2, "random_state": 42}},
    {"name": "shuffle", "params": {"random_state": 42}},
    {"name": "normalize_shape", "params": {}},
    {"name": "divide_by", "params": {"value": 255}},
    {"name": "order", "params": {"order": "th"}}
]

def test_get_nb_samples():
    assert get_nb_samples(toy_pipeline) == 50
    assert get_nb_samples([]) == 0

def test_get_shapes():
    assert get_shapes({}) == {}
    assert get_shapes({'X': np.random.uniform(size=(1,2,3))}) == {'X': (1, 2, 3)}
    assert get_shapes({'X': np.random.uniform(size=(1,2,3)), 'y': np.random.uniform(size=(4, 5))}) == {'X': (1, 2, 3), 'y': (4, 5)}

def test_get_nb_minibatches():
    assert get_nb_minibatches(0, 10) == 0
    assert get_nb_minibatches(0, 1) == 0
    assert get_nb_minibatches(0, 0) == 0
    assert get_nb_minibatches(10, 0) == 0
    assert get_nb_minibatches(25, 1) == 25
    assert get_nb_minibatches(25, 10) == 3

def test_batch_iterator():
    it = BatchIterator(lambda: [], cols=['X', 'y'])
    assert list(it.flow(batch_size=10)) == []

    xvals = np.arange(25).astype(np.float32)
    yvals = xvals ** 2

    data = [{'X': xvals[i], 'y': yvals[i]} for i in range(25)]

    it = BatchIterator(lambda: data, cols=['X', 'y'])
    res = it.flow(batch_size=10, repeat=False)
    res = list(res)
    assert len(res) == 3
    assert len(res[0]['X']) == 10
    assert len(res[0]['y']) == 10
    assert len(res[1]['X']) == 10
    assert len(res[1]['y']) == 10
    assert len(res[2]['X']) == 5
    assert len(res[2]['y']) == 5
    assert np.all(res[0]['X'] == xvals[0:10])
    assert np.all(res[0]['y'] == yvals[0:10])
    assert np.all(res[1]['X'] == xvals[10:20])
    assert np.all(res[1]['y'] == yvals[10:20])
    assert np.all(res[2]['X'] == xvals[20:])
    assert np.all(res[2]['y'] == yvals[20:])