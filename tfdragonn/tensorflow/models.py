from __future__ import absolute_import, division, print_function

from abc import abstractmethod, abstractproperty, ABCMeta
import tensorflow as tf
import tensorflow.contrib.slim as slim

class Classifier(object):
    __metaclass__ = ABCMeta

    @abstractproperty
    def get_inputs(self):
        pass

    @abstractmethod
    def __init__(self, **hyperparameters):
        pass

    @abstractmethod
    def get_logits(inputs):
        pass

    def get_preds(inputs):
        logits = self.get_logits(inputs)
        preds = tf.sigmoid(logits, name="preds")
        return preds

class SequenceAndDnaseClassifier(Classifier):

    @property
    def get_inputs(self):
        return ["genome_data_dir", "dnase_data_dir"]

    def __init__(self, num_tasks=1,
                 num_seq_filters=(25, 25, 25), seq_conv_width=(25, 25, 25),
                 num_dnase_filters=(25, 25, 25), dnase_conv_width=(25, 25, 25),
                 num_combined_filters=(55,), combined_conv_width=(25,)
                 pool_width=25, batch_norm=False):
        assert len(num_seq_filters) == len(seq_conv_width)
        assert len(num_dnase_filters) == len(dnase_conv_width)
        assert len(num_combined_filters) == len(combined_conv_width)

        self.num_tasks = num_tasks
        self.num_seq_filters = num_seq_filters
        self.seq_conv_width = seq_conv_width
        self.num_dnase_filters = num_dnase_filters
        self.dnase_conv_width = dnase_conv_width
        self.pool_width = pool_width
        self.batch_norm = batch_norm
        self.num_combined_filters = num_combined_filters

    def get_logits(inputs):
        with slim.arg_scope([slim.conv2d, slim.fully_connected],
                            reuse=False,
                            activation_fn=tf.nn.relu,
                            weights_initializer=tf.truncated_normal_initializer(stddev=0.1), # change to he_normal
                            biases_initializer=tf.constant_initializer(0.0)):
            seq_preds = inputs["genome_data_dir"]
            for i, (num_filter, filter_width) in enumerate(zip(self.num_seq_filters, self.seq_conv_width)):
                seq_preds = slim.conv2d(seq_preds, num_filter, [4 if i==0 else 1, filter_width], padding='VALID', scope='sequence_conv{:d}'.format(i + 1))
            dnase_preds = inputs["dnase_data_dir"]
            for i, (num_filter, filter_width) in enumerate(zip(self.num_dnase_filters, self.dnase_conv_width)):
                dnase_preds = slim.conv2d(dnase_preds, num_filter, [1, filter_width], padding='VALID', scope='dnase_conv{:d}'.format(i + 1))
            preds = tf.concat(1, [seq_preds, dnase_preds]) # check if concatenation axis is correct
            for i, (num_filter, filter_width) in enumerate(zip(self.num_combined_filters, self.combined_conv_width)):
                preds = slim.conv2d(preds, num_filters, [2 if i==0 else 1, filter_width], padding='VALID', scope='combined_conv{:d}'.format(i + 1))
            preds = slim.avg_pool2d(net, [1, self.pool_width], stride=[1, self.pool_width], padding='VALID', scope='avg_pool')
            preds = slim.flatten(preds)
            preds = slim.fully_connected(preds, self.num_tasks, activation_fn=None, scope='fc')

            return preds
