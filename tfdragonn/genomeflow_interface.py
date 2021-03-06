from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os

import numpy as np
import genomeflow as gf
import tensorflow as tf

from tfdragonn import datasets
from tfdragonn import models

from genomeflow.io.streams import BedFileStream

data_type2extractor = {
    'genome_data_dir': 'bcolz_array',
    'dnase_data_dir': 'bcolz_array',
    'HelT_data_dir': 'bcolz_array',
    'MGW_data_dir': 'bcolz_array',
    'OC2_data_dir': 'bcolz_array',
    'ProT_data_dir': 'bcolz_array',
    'Roll_data_dir': 'bcolz_array',
    'tss_counts': 'bed',
    'dhs_counts': 'bed',
    'tss_mean_tpm': 'bed',
    'tss_max_tpm': 'bed'
}
data_type2options = {
    'tss_counts': {
        'op': 'count'
    },
    'dhs_counts': {
        'op': 'count'
    },
    'tss_mean_tpm': {
        'op': 'mean',
        'norm_params': 'asinh_zscore'
    },
    'tss_max_tpm': {
        'op': 'max',
        'norm_params': 'asinh_zscore'
    }
}


class GenomeFlowInterface(object):

    def __init__(self, datasetspec, intervalspec, modelspec, logdir,
                 shuffle=True, pos_sampling_rate=0.05,
                 validation_chroms=None, holdout_chroms=None,
                 validation_intervalspec=None, logger=None):
        self.datasetspec = datasetspec
        self.intervalspec = intervalspec
        self.validation_intervalspec = validation_intervalspec
        self.modelspec = modelspec
        self.logdir = logdir
        input_names = models.model_inputs_from_config(modelspec)
        self.input_names = [input_name.split('/')[1]
                            for input_name in input_names]
        self.shuffle = shuffle
        self.pos_sampling_rate = pos_sampling_rate
        self.validation_chroms = validation_chroms
        self.holdout_chroms = holdout_chroms
        self.logger = logger
        self.dataset = datasets.parse_inputs_and_intervals(
            datasetspec, intervalspec)
        if self.validation_intervalspec is not None:
            self.validation_dataset = datasets.parse_inputs_and_intervals(
                datasetspec, self.validation_intervalspec)
        self.task_names = self.dataset.values()[0]['task_names']
        self.tmp_files = []
        if self.logger is not None:
            self.logger.info('GenomeFlowInterface Settings:')
            self.logger.info('shuffle: {}'.format(shuffle))
            self.logger.info('pos_sampling_rate: {}'.format(pos_sampling_rate))
            self.logger.info('validation_chroms: {}'.format(validation_chroms))
            self.logger.info('holdout_chroms: {}'.format(holdout_chroms))
    def get_train_queue(self):
        skip_chroms = []
        if self.validation_chroms is not None:
            skip_chroms += self.validation_chroms
        if self.holdout_chroms is not None:
            skip_chroms += self.holdout_chroms
        return self.get_queue(self.dataset,
                              holdout_chroms=skip_chroms,
                              pos_sampling_rate=self.pos_sampling_rate,
                              input_names=self.input_names,
                              shuffle=self.shuffle)

    def get_validation_queue(self, num_epochs=1, asynchronous_enqueues=False,
                             enqueues_per_thread=[128, 1]):
        selected_chroms = self.validation_chroms
        if self.validation_intervalspec is not None:
            return self.get_queue(
                self.validation_dataset,
                selected_chroms=selected_chroms,
                holdout_chroms=self.holdout_chroms,
                num_epochs=num_epochs,
                asynchronous_enqueues=asynchronous_enqueues,
                input_names=self.input_names,
                enqueues_per_thread=enqueues_per_thread)
        else:
            return self.get_queue(
                self.dataset,
                selected_chroms=selected_chroms,
                holdout_chroms=self.holdout_chroms,
                num_epochs=num_epochs,
                asynchronous_enqueues=asynchronous_enqueues,
                input_names=self.input_names,
                enqueues_per_thread=enqueues_per_thread)

    def get_interval_queue(self, dataset, dataset_id, selected_chroms=None,
                           holdout_chroms=None, num_epochs=None,
                           read_batch_size=10000, shuffle=True, pos_sampling_rate=None):
        intervals_file = dataset['intervals_file']
        if pos_sampling_rate is not None:
            def pos_sampling_fn(record):
                # single task only
                return np.array(record[-1], dtype=np.int32)[0] == 1

            def neg_sampling_fn(record):
                return np.array(record[-1], dtype=np.int32)[0] == 0
            pos_only_stream = BedFileStream(
                intervals_file,
                selected_chroms=selected_chroms,
                holdout_chroms=holdout_chroms,
                num_epochs=1,
                sampling_fn=pos_sampling_fn)
            neg_only_stream = BedFileStream(
                intervals_file,
                selected_chroms=selected_chroms,
                holdout_chroms=holdout_chroms,
                num_epochs=1,
                sampling_fn=neg_sampling_fn)
            neg_dest_file = os.path.join(
                self.logdir, os.path.basename(intervals_file) + 'neg')
            pos_dest_file = os.path.join(
                self.logdir, os.path.basename(intervals_file) + 'pos')
            print(neg_dest_file)
            print(pos_dest_file)
	    # while os.path.isfile(neg_dest_file):
                # neg_dest_file += str(np.random.randint(low=0, high=10))
            # while os.path.isfile(pos_dest_file):
                # pos_dest_file += str(np.random.randint(low=0, high=10))
            # self.tmp_files += [neg_dest_file, pos_dest_file]
            # pos queue
	    if not os.path.isfile(pos_dest_file) or os.path.getsize(pos_dest_file) == 0:
		with open(pos_dest_file, 'w') as pos_dest_fp:
			print("Creating new pos dest file")
			while True:
			    try:
				entry = pos_only_stream.read_entry()
			    except tf.errors.OutOfRangeError as e:
				print("Out of range error")
				break
			    if entry['chrom'] in holdout_chroms:
				raise ValueError('Chromosome cannot be in holdout chromosomes')
			    line = '\t'.join(
				map(str, map(entry.get, ['chrom', 'start', 'end'])))
			    if 'labels' in entry:
				line += '\t' + '\t'.join([str(i)
							  for i in entry['labels'].tolist()])
			    # print(line)
			    pos_dest_fp.write(line + '\n')

            print(dataset_id)
	    pos_interval_queue = gf.io.StreamingIntervalQueue(
                pos_dest_file,
                read_batch_size=read_batch_size,
                name='{}-pos-interval-queue'.format(dataset_id),
                num_epochs=num_epochs,
                capacity=50000,
                shuffle=shuffle,
                min_after_dequeue=40000,
                summary=True)
	    print("Made pos interval queue")
            # neg only queue
	    if not os.path.isfile(neg_dest_file) or os.path.getsize(neg_dest_file) == 0:
		    with open(neg_dest_file, 'w') as neg_dest_fp:
			print("Rewriting negative dest file")
			while True:
			    try:
				entry = neg_only_stream.read_entry()
			    except tf.errors.OutOfRangeError as e:
				break
			    if entry['chrom'] in holdout_chroms:
				raise ValueError('Chromosome cannot be in holdout chromosomes')
			    line = '\t'.join(
				map(str, map(entry.get, ['chrom', 'start', 'end'])))
			    if 'labels' in entry:
				line += '\t' + '\t'.join([str(i)
							  for i in entry['labels'].tolist()])
				neg_dest_fp.write(line + '\n')
            neg_interval_queue = gf.io.StreamingIntervalQueue(
                neg_dest_file,
                read_batch_size=read_batch_size,
                name='{}-neg-interval-queue'.format(dataset_id),
                num_epochs=num_epochs,
                capacity=50000,
                shuffle=shuffle,
                min_after_dequeue=40000,
                summary=True)
	    print("Made neg dest queue")
            interval_queues = {
                pos_interval_queue: pos_sampling_rate,
                neg_interval_queue: 1 - pos_sampling_rate,
            }
            shared_interval_queue = gf.io.SharedIntervalQueue(
                interval_queues,
                capacity=50000,
                name='{}-shared-interval-queue'.format(dataset_id))
            return shared_interval_queue
        else:
            dest_file = os.path.join(
                self.logdir, os.path.basename(intervals_file))
            while os.path.isfile(dest_file):
                dest_file += str(np.random.randint(low=0, high=10))
            self.tmp_files.append(dest_file)
            source_stream = BedFileStream(
                intervals_file, selected_chroms=selected_chroms, holdout_chroms=holdout_chroms, num_epochs=1)
            with open(dest_file, 'w') as dest_fp:
                while True:
                    try:
                        entry = source_stream.read_entry()
                    except tf.errors.OutOfRangeError as e:
                        break
                    line = '\t'.join(
                        map(str, map(entry.get, ['chrom', 'start', 'end'])))
                    if 'labels' in entry:
                        line += '\t' + '\t'.join([str(i)
                                                  for i in entry['labels'].tolist()])
                    dest_fp.write(line + '\n')

            interval_queue = gf.io.StreamingIntervalQueue(
                dest_file,
                read_batch_size=read_batch_size,
                name='{}-interval-queue'.format(dataset_id),
                num_epochs=num_epochs,
                capacity=50000,
                shuffle=shuffle,
                min_after_dequeue=40000,
                summary=True)
            return interval_queue

    def get_queue(self, dataset, selected_chroms=None, holdout_chroms=None,
                  num_epochs=None, asynchronous_enqueues=True,
                  pos_sampling_rate=None, input_names=None, shuffle=False,
                  enqueues_per_thread=[128]):
        # print(dataset.items())
	examples_queues = {
            dataset_id: self.get_example_queue(dataset_values, dataset_id,
                                               holdout_chroms=holdout_chroms,
                                               selected_chroms=selected_chroms,
                                               num_epochs=num_epochs,
                                               pos_sampling_rate=pos_sampling_rate,
                                               input_names=input_names,
                                               shuffle=shuffle,
                                               enqueues_per_thread=enqueues_per_thread)
            for dataset_id, dataset_values in dataset.items()
        }
        shared_examples_queue = self.get_shared_examples_queue(
            examples_queues, asynchronous_enqueues=asynchronous_enqueues,
            enqueues_per_thread=enqueues_per_thread)
        return shared_examples_queue

    def get_example_queue(self, dataset, dataset_id, selected_chroms=None,
                          holdout_chroms=None, num_epochs=None, pos_sampling_rate=None,
                          input_names=None, shuffle=False, enqueues_per_thread=[128]):
        interval_queue = self.get_interval_queue(
            dataset, dataset_id, selected_chroms=selected_chroms,
            holdout_chroms=holdout_chroms, num_epochs=num_epochs,
            read_batch_size=1, pos_sampling_rate=pos_sampling_rate, shuffle=shuffle)
        inputs = dataset['inputs']
        if input_names is not None:  # use only these inputs in the example queue
            assert all([input_name in inputs.keys()
                        for input_name in input_names])
            data_sources = {k: self.get_data_source(k, v) for k, v in inputs.items()
                            if k in input_names}
        else:
            data_sources = {k: self.get_data_source(
                k, v) for k, v in inputs.items()}

        examples_queue = gf.io.ExampleQueue(
            interval_queue, data_sources, enqueues_per_thread=enqueues_per_thread,
            capacity=2048, name='{}-example-queue'.format(dataset_id))

        return examples_queue

    def get_shared_examples_queue(self, examples_queues, asynchronous_enqueues=True,
                                  enqueues_per_thread=[128]):
        shared_examples_queue = gf.io.MultiDatasetExampleQueue(
            examples_queues, enqueues_per_thread=enqueues_per_thread,
            capacity=2048, name='multi-dataset-example-queue',
            asynchronous_enqueues=asynchronous_enqueues)
        return shared_examples_queue

    def get_data_source(self, data_type, data_specs):
        """
        data_specs is either the file path for bcolz data
        or dictionary with specs for bed data.
        """
        extractor_type = data_type2extractor[data_type]
        options = {}
        data_path = data_specs
        if extractor_type == 'bed':  # parse data specs
            data_path = data_specs['filepath']
            options = data_type2options[data_type].copy()
            options.update(data_specs['options'])
        return gf.io.DataSource(data_path, extractor_type, options)

    def cleanup_tmp_files(self):
        for fpath in self.tmp_files:
            if os.path.exists(fpath):
                os.system('rm -f {}'.format(fpath))

    def __del__(self):
        self.cleanup_tmp_files()

    @property
    def normalized_class_rates(self):
        """sampling rate / true rate"""
        if len(self.task_names) > 1:
            return None
        if self.pos_sampling_rate is None:
            return 1

        total = num_positives = 0
        for dataset_id, dataset in self.dataset.items():
            labels = dataset['labels']
            num_positives += np.sum(labels == 1)
            total += labels.shape[0]

        pos_rate = num_positives / total
        neg_rate = 1 - pos_rate

        normalized_pos_rate = pos_rate / self.pos_sampling_rate
        normalized_neg_rate = neg_rate / self.pos_sampling_rate

        return {'positive': normalized_pos_rate,
                'negative': normalized_neg_rate}
