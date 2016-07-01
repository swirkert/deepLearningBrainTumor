__author__ = 'fabian'
import numpy as np
import matplotlib.pyplot as plt
import lasagne
from memmap_negPos_batchgen import memmapGenerator
from numpy import memmap
import cPickle

def threaded_generator(generator, num_cached=10):
    # this code is writte by jan Schluter
    # copied from https://github.com/benanne/Lasagne/issues/12
    import Queue
    queue = Queue.Queue(maxsize=num_cached)
    sentinel = object()  # guaranteed unique reference

    # define producer (putting items into queue)
    def producer():
        for item in generator:
            queue.put(item)
        queue.put(sentinel)

    # start producer (in a background thread)
    import threading
    thread = threading.Thread(target=producer)
    thread.daemon = True
    thread.start()

    # run as consumer (read items from queue, in current thread)
    item = queue.get()
    while item is not sentinel:
        yield item
        queue.task_done()
        item = queue.get()


def printLosses(all_training_losses, all_training_accs, all_validation_losses, all_valid_accur, fname, samplesPerEpoch=10):
    fig, ax1 = plt.subplots()
    trainLoss_x_values = np.arange(1/float(samplesPerEpoch), len(all_training_losses)/float(samplesPerEpoch)+0.000001, 1/float(samplesPerEpoch))
    val_x_values = np.arange(1, len(all_validation_losses)+0.001, 1)
    ax1.plot(trainLoss_x_values, all_training_losses, 'b--')
    ax1.plot(val_x_values, all_validation_losses, color='b')
    ax1.set_ylabel('loss')
    ax1.set_xlabel('epoch')

    ax2 = ax1.twinx()
    ax2.plot(trainLoss_x_values, all_training_accs, 'r--')
    ax2.plot(val_x_values, all_valid_accur, color='r')
    ax2.set_ylabel('accuracy')
    for t2 in ax2.get_yticklabels():
        t2.set_color('r')

    ax1.legend(['trainLoss', 'validLoss'], loc=0)
    ax2.legend(['trainAcc', 'validAcc'], loc=2)
    # ax2.legend(['valAccuracy'])
    plt.savefig(fname)
    plt.close()


def validate_result(img, convLayer):
    img_for_cnn = img[np.newaxis, np.newaxis, :, :]
    filtered_by_cnn = lasagne.layers.get_output(convLayer, img_for_cnn).eval()
    plt.figure(figsize=(12, 12))
    for i in xrange(filtered_by_cnn.shape[1]):
        plt.subplot(int(np.ceil(np.sqrt(filtered_by_cnn.shape[1]))), int(np.ceil(np.sqrt(filtered_by_cnn.shape[1]))), i+1)
        plt.imshow(filtered_by_cnn[0, i, :, :], cmap="gray", interpolation="nearest")
        plt.axis('off')
    plt.savefig("../results/filtered_by_cnn.png")
    plt.close()

    weights_w = convLayer.get_params()[0].get_value()
    weights_b = convLayer.get_params()[1].get_value()

    from scipy.signal import convolve2d
    res_scipy = []
    numFilters = weights_w.shape[0]
    for i in xrange(numFilters):
        weights = weights_w[i, 0, :, :]
        res_scipy.append(lasagne.nonlinearities.rectify(convolve2d(img, weights, mode='same') + weights_b[i]))

    plt.figure(figsize=(12, 12))
    for i in xrange(numFilters):
        plt.subplot(int(np.ceil(np.sqrt(numFilters))), int(np.ceil(np.sqrt(numFilters))), i+1)
        plt.imshow(res_scipy[i], cmap="gray", interpolation="nearest")
        plt.axis('off')
    plt.savefig("../results/filtered_by_scipy.png")
    plt.close()

def plot_some_data():
    with open("../data/patchClassification_memmap_properties.pkl", 'r') as f:
        memmap_properties = cPickle.load(f)
    n_pos_train = memmap_properties["train_pos"]
    n_neg_train = memmap_properties["train_neg"]
    n_pos_val = memmap_properties["val_pos"]
    n_neg_val = memmap_properties["val_neg"]
    train_pos_memmap = memmap("../data/patchClassification_train_pos.memmap", dtype=np.float32, mode="r+", shape=memmap_properties["train_pos_shape"])
    train_neg_memmap = memmap("../data/patchClassification_train_neg.memmap", dtype=np.float32, mode="r+", shape=memmap_properties["train_neg_shape"])
    val_pos_memmap = memmap("../data/patchClassification_val_pos.memmap", dtype=np.float32, mode="r+", shape=memmap_properties["val_pos_shape"])
    val_neg_memmap = memmap("../data/patchClassification_val_neg.memmap", dtype=np.float32, mode="r+", shape=memmap_properties["val_neg_shape"])
    i = 0
    ctr = 0
    for data, seg, labels in memmapGenerator(train_neg_memmap, train_pos_memmap, 128, n_pos_train, n_neg_train):
        if i == 2:
            break
        for img, segm, lab in zip(data, seg, labels):
            plt.figure(figsize=(12,12))
            img = np.array(img[0]) # dont write into memmap
            img = np.repeat(img[np.newaxis, :, :], 3, 0)
            img = img.transpose((1, 2, 0))
            img[:, :, 0][segm[0] > 1] *= 1.0
            plt.imshow(img, interpolation='nearest')
            if lab == 0:
                color = 'green'
            else:
                color = 'red'
            plt.text(0, 0, lab, color=color, bbox=dict(facecolor='white', alpha=1))
            plt.savefig("../some_images/img_%04.0f.png"%ctr)
            plt.close()
            ctr += 1
        i += 1


def plot_layer_weights(layer):
    conv_1_1_weights = layer.get_params()[0].get_value()

    plt.figure(figsize=(12, 12))
    for i in range(conv_1_1_weights.shape[0]):
        plt.subplot(int(np.ceil(np.sqrt(conv_1_1_weights.shape[0]))), int(np.ceil(np.sqrt(conv_1_1_weights.shape[0]))), i+1)
        plt.imshow(conv_1_1_weights[i, 0, :, :], cmap="gray", interpolation="nearest")
        plt.axis('off')
    plt.show()