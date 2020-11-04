"""
Replay and experiment
=====================

In a previous example, we have shown how experiments can be resumed.
Cardinal also allows for experiments to be replayed, meaning that
one can save intermediate data to be able to run analysis on the
experiment without having to retrain all the models. Let us now
see how the ReplayCache allows it.
"""

import shutil
import os
import numpy as np
import dataset

from sklearn.datasets import load_iris
from sklearn.svm import SVC
from sklearn.model_selection import train_test_split

from cardinal.random import RandomSampler
from cardinal.uncertainty import MarginSampler
from cardinal.cache import ReplayCache
from cardinal.utils import GrowingIndex

##############################################################################
# Since we will be looking at the cache, we need a utility function to display
# a tree folder.

def print_folder_tree(startpath):
    for root, dirs, files in os.walk(startpath):
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * (level)
        print('{}{}/'.format(indent, os.path.basename(root)))
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            print('{}{}'.format(subindent, f))

#############################################################################
# We load the data and define the parameters of this experiment:  
#
# * ``batch_size`` is the number of samples that will be annotated and added to
#   the training set at each iteration,
# * ``n_iter`` is the number of iterations in our simulation

iris = load_iris()
X = iris.data
y = iris.target

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.5, random_state=1)
batch_size = 5
n_iter = 10

model = SVC(probability=True)

sampler = MarginSampler(model, batch_size)
config = dict(sampler='margin')

#############################################################################
# We define our experiment in a dedicated function since we want to run it
# several times. We also create a dedicated exception that we will rise to
# simulate an interruption in the experiment.
#
# Note the use of the GrowingIndex utils that facilitate the handing of
# indices in an active learning experiment.


with ReplayCache('./cache', './cache.db', keys=config) as cache:

    index = GrowingIndex(X_train.shape[0])

    # Add at least one sample from each class
    index.add_to_selected([np.where(y_train == i)[0][0] for i in np.unique(y)])

    selected = cache.persisted_value('selected', index.selected)
    predictions = cache.persisted_value('prediction', None)

    for j, prev_selected, prev_predictions in cache.iter(range(n_iter), selected.previous(), predictions.previous()):
        print('Computing iteration {}'.format(j))
        index.resume(prev_selected)

        model.fit(X_train[prev_selected], y_train[prev_selected])
        sampler.fit(X_train[prev_selected], y_train[prev_selected])
        index.add_to_selected(sampler.select_samples(X_train[index.non_selected]))
        selected.set(index.selected)
        predictions.set(model.predict(X_test))



#############################################################################
# All values for all iterations are kept. The cache structure is human
# readable and can be shared for better reproducibility.

    print_folder_tree('./cache')


#############################################################################
# If we forgot to compute contradictions during the experiment, we can do it
# now.

    def compute_contradictions(previous_prediction, current_prediction):
        if previous_prediction is None:
            return 0
        return (previous_prediction != current_prediction).sum()

    cache.compute_metric('contradictions', compute_contradictions, predictions.previous(), predictions.current())

    from matplotlib import pyplot as plt

    iteration = []
    contradictions = []

    for r in dataset.connect('sqlite:///cache.db')['contradictions'].all():
        iteration.append(r['iteration'])
        contradictions.append(r['value'])

    plt.plot(iteration, contradictions)
    plt.xlabel('Iteration')
    plt.ylabel('Contradictions')
    plt.title('Evolution of Contradictions during active learning experiment on Iris dataset')
    plt.show()


#############################################################################
# We clean all the cache folder.

shutil.rmtree('./cache')
os.remove('./cache.db')