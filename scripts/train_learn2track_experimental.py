#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

# Hack so you don't have to put the library containing this script in the PYTHONPATH.
sys.path = [os.path.abspath(os.path.join(__file__, '..', '..'))] + sys.path

import pickle
import shutil
import numpy as np
from os.path import join as pjoin
import argparse

import theano
import nibabel as nib

from time import sleep

import theano.tensor as T

from smartlearner import Trainer, tasks, Dataset
from smartlearner import tasks
from smartlearner import stopping_criteria
from smartlearner import views
from smartlearner import utils as smartutils
from smartlearner.optimizers import SGD, AdaGrad, Adam
from smartlearner.direction_modifiers import ConstantLearningRate, DirectionClipping


from learn2track import utils
from learn2track.utils import Timer, load_ismrm2015_challenge, load_ismrm2015_challenge_contiguous
from learn2track.lstm import LSTM_Regression, LSTM_RegressionWithFeaturesExtraction, LSTM_Softmax, LSTM_Hybrid
from learn2track.factories import ACTIVATION_FUNCTIONS
from learn2track.factories import WEIGHTS_INITIALIZERS, weigths_initializer_factory
from learn2track.factories import optimizer_factory
#from learn2track.view import RegressionError

from learn2track.losses import L2DistanceWithBinaryCrossEntropy, L2DistanceForSequences, NLLForSequenceOfDirections, ErrorForSequenceOfDirections
from learn2track.losses import ErrorForSequenceWithClassTarget, NLLForSequenceWithClassTarget
from learn2track.batch_schedulers import BundlesBatchScheduler, SequenceBatchScheduler
from learn2track.batch_schedulers import BundlesBatchSchedulerWithClassTarget, SequenceBatchSchedulerWithClassTarget

# DATASETS = ["ismrm2015_challenge"]
MODELS = ['lstm', 'gru', 'lstm_hybrid', 'lstm_extraction']


def build_train_lstm_argparser(subparser):
    DESCRIPTION = "Train a LSTM."

    p = subparser.add_parser("lstm", description=DESCRIPTION, help=DESCRIPTION)

    # p.add_argument('dataset', type=str, help='folder containing training data (.npz files).')

    # Model options (LSTM)
    model = p.add_argument_group("LSTM arguments")

    model.add_argument('--hidden-sizes', type=int, nargs='+', default=500,
                       help="Size of the hidden layers. Default: 500")

    model.add_argument('--hidden-activation', type=str, choices=ACTIVATION_FUNCTIONS, default=ACTIVATION_FUNCTIONS[0],
                       help="Activation functions: {}".format(ACTIVATION_FUNCTIONS),)
    model.add_argument('--weights-initialization', type=str, default=WEIGHTS_INITIALIZERS[0], choices=WEIGHTS_INITIALIZERS,
                       help='which type of initialization to use when creating weights [{0}].'.format(", ".join(WEIGHTS_INITIALIZERS)))
    model.add_argument('--initialization-seed', type=int, default=1234,
                       help='seed used to generate random numbers. Default=1234')

    # General parameters (optional)
    general = p.add_argument_group("General arguments")
    general.add_argument('-f', '--force', action='store_true', help='restart training from scratch instead of resuming.')


def build_train_gru_argparser(subparser):
    DESCRIPTION = "Train a GRU."

    p = subparser.add_parser("gru", description=DESCRIPTION, help=DESCRIPTION)

    # p.add_argument('dataset', type=str, help='folder containing training data (.npz files).')

    # Model options (GRU)
    model = p.add_argument_group("GRU arguments")

    model.add_argument('--hidden-sizes', type=int, nargs='+', default=500,
                       help="Size of the hidden layers. Default: 500")

    model.add_argument('--hidden-activation', type=str, choices=ACTIVATION_FUNCTIONS, default=ACTIVATION_FUNCTIONS[0],
                       help="Activation functions: {}".format(ACTIVATION_FUNCTIONS),)
    model.add_argument('--weights-initialization', type=str, default=WEIGHTS_INITIALIZERS[0], choices=WEIGHTS_INITIALIZERS,
                       help='which type of initialization to use when creating weights [{0}].'.format(", ".join(WEIGHTS_INITIALIZERS)))
    model.add_argument('--initialization-seed', type=int, default=1234,
                       help='seed used to generate random numbers. Default=1234')

    # General parameters (optional)
    general = p.add_argument_group("General arguments")
    general.add_argument('-f', '--force', action='store_true', help='restart training from scratch instead of resuming.')


def build_train_lstm_hybrid_argparser(subparser):
    DESCRIPTION = "Train a LSTM Hybrid."

    p = subparser.add_parser("lstm_hybrid", description=DESCRIPTION, help=DESCRIPTION)

    # p.add_argument('dataset', type=str, help='folder containing training data (.npz files).')

    # Model options (LSTM)
    model = p.add_argument_group("LSTM Hybrid arguments")

    model.add_argument('--hidden-sizes', type=int, nargs='+', default=500,
                       help="Size of the hidden layers. Default: 500")

    model.add_argument('--hidden-activation', type=str, choices=ACTIVATION_FUNCTIONS, default=ACTIVATION_FUNCTIONS[0],
                       help="Activation functions: {}".format(ACTIVATION_FUNCTIONS),)
    model.add_argument('--weights-initialization', type=str, default=WEIGHTS_INITIALIZERS[0], choices=WEIGHTS_INITIALIZERS,
                       help='which type of initialization to use when creating weights [{0}].'.format(", ".join(WEIGHTS_INITIALIZERS)))
    model.add_argument('--initialization-seed', type=int, default=1234,
                       help='seed used to generate random numbers. Default=1234')

    # General parameters (optional)
    general = p.add_argument_group("General arguments")
    general.add_argument('-f', '--force', action='store_true', help='restart training from scratch instead of resuming.')


def build_train_lstm_extraction_argparser(subparser):
    DESCRIPTION = "Train a LSTM that has a features extraction as the first layer."

    p = subparser.add_parser("lstm_extraction", description=DESCRIPTION, help=DESCRIPTION)

    # p.add_argument('dataset', type=str, help='folder containing training data (.npz files).')

    # Model options (LSTM)
    model = p.add_argument_group("LSTM arguments")

    model.add_argument('--features-size', type=int, default=250,
                       help="Size of the features space (i.e. the first layer). Default: 250")

    model.add_argument('--hidden-sizes', type=int, nargs='+', default=500,
                       help="Size of the hidden layers. Default: 500")

    model.add_argument('--hidden-activation', type=str, choices=ACTIVATION_FUNCTIONS, default=ACTIVATION_FUNCTIONS[0],
                       help="Activation functions: {}".format(ACTIVATION_FUNCTIONS),)
    model.add_argument('--weights-initialization', type=str, default=WEIGHTS_INITIALIZERS[0], choices=WEIGHTS_INITIALIZERS,
                       help='which type of initialization to use when creating weights [{0}].'.format(", ".join(WEIGHTS_INITIALIZERS)))
    model.add_argument('--initialization-seed', type=int, default=1234,
                       help='seed used to generate random numbers. Default=1234')

    # General parameters (optional)
    general = p.add_argument_group("General arguments")
    general.add_argument('-f', '--force', action='store_true', help='restart training from scratch instead of resuming.')


def buildArgsParser():
    DESCRIPTION = ("Script to train a LSTM model on a dataset"
                   " (ismrm2015_challenge) using Theano.")
    p = argparse.ArgumentParser(description=DESCRIPTION)

    # Dataset options
    dataset = p.add_argument_group("Dataset")
    dataset.add_argument('dataset', type=str, help='folder containing training data (.npz files).')
    dataset.add_argument('--nb-updates-per-epoch', type=int,
                         help=('If specified, a batch will be composed of streamlines drawn from each different bundle (similar amount) each update.'
                               ' Default: go through all streamlines in the trainset exactly sonce.'))
    dataset.add_argument('--append-previous-direction', action="store_true",
                         help="if specified, the target direction of the last timestep will be concatenated to the input of the current timestep. (0,0,0) will be used for the first timestep.")
    dataset.add_argument('--scheduled-sampling', action="store_true",
                         help="if specified, scheduled sampling is used (forces --append-previous-direction).")

    duration = p.add_argument_group("Training duration options")
    duration.add_argument('--max-epoch', type=int, metavar='N', help='if specified, train for a maximum of N epochs.')
    duration.add_argument('--lookahead', type=int, metavar='K', default=10,
                          help='use early stopping with a lookahead of K. Default: 10')
    duration.add_argument('--lookahead-eps', type=float, default=1e-3,
                          help='in early stopping, an improvement is whenever the objective improve of at least `eps`. Default: 1e-3',)

    # Training options
    training = p.add_argument_group("Training options")
    training.add_argument('--batch-size', type=int,
                          help='size of the batch to use when training the model. Default: 100.', default=100)
    training.add_argument('--sequence-length', type=int,
                          help='size of every training sequence. Default: 10.', default=10)
    training.add_argument('--clip-gradient', type=float,
                          help='if provided, gradient norms will be clipped to this value (if it exceed it).')

    # Optimizer options
    optimizer = p.add_argument_group("Optimizer (required)")
    optimizer = optimizer.add_mutually_exclusive_group(required=True)
    optimizer.add_argument('--SGD', metavar="LR", type=str, help='use SGD with constant learning rate for training.')
    optimizer.add_argument('--AdaGrad', metavar="LR [EPS=1e-6]", type=str, help='use AdaGrad for training.')
    optimizer.add_argument('--Adam', metavar="[LR=0.0001]", type=str, help='use Adam for training.')
    optimizer.add_argument('--RMSProp', metavar="LR", type=str, help='use RMSProp for training.')
    optimizer.add_argument('--Adadelta', action="store_true", help='use Adadelta for training.')

    # Task
    task = p.add_argument_group("Task (required)")
    task = task.add_mutually_exclusive_group(required=True)
    task.add_argument('--regression', action="store_true", help='consider this problem as a regression task.')
    task.add_argument('--classification', action="store_true", help='consider this problem as a classification task.')

    # General options (optional)
    general = p.add_argument_group("General arguments")
    general.add_argument('--name', type=str,
                         help='name of the experiment. Default: name is generated from arguments.')

    general.add_argument('-f', '--force', action='store_true', help='restart training from scratch instead of resuming.')
    general.add_argument('--view', action='store_true', help='display learning curves.')

    subparser = p.add_subparsers(title="Models", dest="model")
    subparser.required = True   # force 'required' testing
    build_train_lstm_argparser(subparser)
    build_train_lstm_extraction_argparser(subparser)
    build_train_lstm_hybrid_argparser(subparser)
    build_train_gru_argparser(subparser)

    return p


def maybe_create_experiment_folder(args):
    # Extract experiments hyperparameters
    hyperparams = dict(vars(args))

    # Remove hyperparams that should not be part of the hash
    del hyperparams['max_epoch']
    del hyperparams['force']
    del hyperparams['name']

    # Get/generate experiment name
    experiment_name = args.name
    if experiment_name is None:
        experiment_name = utils.generate_uid_from_string(repr(hyperparams))

    # Create experiment folder
    experiment_path = pjoin(".", "experiments", experiment_name)
    resuming = False
    if os.path.isdir(experiment_path) and not args.force:
        resuming = True
        print("### Resuming experiment ({0}). ###\n".format(experiment_name))
        # Check if provided hyperparams match those in the experiment folder
        hyperparams_loaded = smartutils.load_dict_from_json_file(pjoin(experiment_path, "hyperparams.json"))
        if hyperparams != hyperparams_loaded:
            print("{\n" + "\n".join(["{}: {}".format(k, hyperparams[k]) for k in sorted(hyperparams.keys())]) + "\n}")
            print("{\n" + "\n".join(["{}: {}".format(k, hyperparams_loaded[k]) for k in sorted(hyperparams_loaded.keys())]) + "\n}")
            print("The arguments provided are different than the one saved. Use --force if you are certain.\nQuitting.")
            sys.exit(1)
    else:
        if os.path.isdir(experiment_path):
            shutil.rmtree(experiment_path)

        os.makedirs(experiment_path)
        smartutils.save_dict_to_json_file(pjoin(experiment_path, "hyperparams.json"), hyperparams)

    return experiment_path, hyperparams, resuming


def main():
    parser = buildArgsParser()
    args = parser.parse_args()
    print(args)

    experiment_path, hyperparams, resuming = maybe_create_experiment_folder(args)
    if resuming:
        print("Resuming:", experiment_path)
    else:
        print("Creating:", experiment_path)

    with Timer("Loading dataset"):
        if args.nb_updates_per_epoch is None:
            trainset, validset, testset = load_ismrm2015_challenge_contiguous(args.dataset, args.classification)
            if args.classification:
                batch_scheduler = SequenceBatchSchedulerWithClassTarget(trainset, args.batch_size)
            elif args.regression:
                batch_scheduler = SequenceBatchScheduler(trainset, args.batch_size, args.append_previous_direction or args.scheduled_sampling)

        else:
            trainset, validset, testset = load_ismrm2015_challenge(args.dataset, args.classification)
            if args.classification:
                batch_scheduler = BundlesBatchSchedulerWithClassTarget(trainset, args.batch_size)
            elif args.regression:
                batch_scheduler = BundlesBatchScheduler(trainset, args.batch_size)

            batch_scheduler.nb_updates_per_epoch = args.nb_updates_per_epoch

        print("Datasets:", len(trainset), len(validset), len(testset))
        print ("An epoch will be composed of {} updates.".format(batch_scheduler.nb_updates_per_epoch))

    with Timer("Creating model"):
        input_size = trainset.input_shape[-1] + 3*(args.append_previous_direction or args.scheduled_sampling)
        output_size = trainset.target_shape[-1]
        if args.regression:
            if args.model == "lstm":
                model = LSTM_Regression(input_size, args.hidden_sizes, output_size)
            elif args.model == "lstm_extraction":
                model = LSTM_RegressionWithFeaturesExtraction(input_size, args.features_size, args.hidden_sizes, output_size)
            elif args.model == "gru":
                if args.scheduled_sampling:
                    from learn2track.gru import GRU_RegressionWithScheduledSampling
                    model = GRU_RegressionWithScheduledSampling(input_size, args.hidden_sizes, output_size)
                else:
                    from learn2track.gru import GRU_Regression
                    model = GRU_Regression(input_size, args.hidden_sizes, output_size)

        elif args.classification:
            from dipy.data import get_sphere
            sphere = get_sphere("repulsion724")  # All possible directions (normed)
            sphere.vertices = sphere.vertices.astype(theano.config.floatX)

            if args.model == "lstm":
                model = LSTM_Softmax(input_size, args.hidden_sizes, len(sphere.vertices))
            elif args.model == "lstm_hybrid":
                model = LSTM_Hybrid(input_size, args.hidden_sizes, len(sphere.vertices))

        model.initialize(weigths_initializer_factory(args.weights_initialization,
                                                     seed=args.initialization_seed))

    with Timer("Building optimizer"):
        if args.regression:
            loss = L2DistanceForSequences(model, trainset)

        elif args.classification:
            # loss = NLLForSequenceOfDirections(model, trainset)
            loss = NLLForSequenceWithClassTarget(model, trainset)

        if args.clip_gradient is not None:
            loss.append_gradient_modifier(DirectionClipping(threshold=args.clip_gradient))

        optimizer = optimizer_factory(hyperparams, loss)

    with Timer("Building trainer"):
        trainer = Trainer(optimizer, batch_scheduler)

        # Print time for one epoch
        trainer.append_task(tasks.PrintEpochDuration())
        trainer.append_task(tasks.PrintTrainingDuration())

        # Log training error
        loss_monitor = views.MonitorVariable(loss.loss)
        avg_loss = tasks.AveragePerEpoch(loss_monitor)
        trainer.append_task(avg_loss)

        # Print average training loss.
        # trainer.append_task(tasks.Print("Avg. training loss:     : {}", avg_loss))

        if args.classification and args.model == "lstm_hybrid":
            mask = trainset.symb_mask
            targets_directions = smartutils.sharedX(sphere.vertices)[T.cast(trainset.symb_targets[:, :, 0], dtype="int32")]
            reconstruction_error = T.sum(((model.directions - targets_directions)**2), axis=2)
            avg_reconstruction_error_per_sequence = T.sum(reconstruction_error*mask, axis=1)  # / T.sum(mask, axis=1)
            # avg_reconstruction_error_monitor = views.MonitorVariable(T.mean(avg_reconstruction_error_per_sequence))
            avg_reconstruction_error_monitor = views.MonitorVariable(T.sum(avg_reconstruction_error_per_sequence))
            avg_reconstruction_error = tasks.AveragePerEpoch(avg_reconstruction_error_monitor)
            trainer.append_task(avg_reconstruction_error)
            trainer.append_task(tasks.Print("Avg. reconstruction error:     : {}", avg_reconstruction_error))

        # Print NLL mean/stderror.
        if args.regression:
            # train_loss = L2DistanceForSequences(model, trainset)
            # train_batch_scheduler = SequenceBatchScheduler(trainset, batch_size=50, append_previous_direction=args.append_previous_direction or args.scheduled_sampling)
            # train_error = views.LossView(loss=train_loss, batch_scheduler=train_batch_scheduler)
            # trainer.append_task(tasks.Print("Trainset - Error        : {0:.2f} | {1:.2f}", train_error.sum, train_error.mean))

            valid_loss = L2DistanceForSequences(model, validset)
            valid_batch_scheduler = SequenceBatchScheduler(validset, batch_size=50, append_previous_direction=args.append_previous_direction or args.scheduled_sampling)
            valid_error = views.LossView(loss=valid_loss, batch_scheduler=valid_batch_scheduler)
            trainer.append_task(tasks.Print("Validset - Error        : {0:.2f} | {1:.2f}", valid_error.sum, valid_error.mean))

            lookahead_loss = valid_error.sum

            gradient_norm = views.MonitorVariable(T.sqrt(sum(map(lambda d: T.sqr(d).sum(), loss.orig_gradients.values()))))
            trainer.append_task(tasks.Print("||g|| : {0:.4f}", gradient_norm))

            gradient_norm_clipped = views.MonitorVariable(T.sqrt(sum(map(lambda d: T.sqr(d).sum(), loss.gradients.values()))))
            trainer.append_task(tasks.Print("||g'|| : {0:.4f}", gradient_norm_clipped))

            # logger = tasks.Logger(train_error.mean, valid_error.mean, gradient_norm, gradient_norm_clipped)
            logger = tasks.Logger(valid_error.mean, gradient_norm, gradient_norm_clipped)
            trainer.append_task(logger)

            if args.view:
                import pylab as plt

                def _plot(*args, **kwargs):
                    plt.figure(1)
                    plt.clf()
                    plt.show(False)
                    plt.subplot(121)
                    plt.plot(np.array(logger.get_variable_history(0)).flatten(), label="Train")
                    plt.plot(np.array(logger.get_variable_history(1)).flatten(), label="Valid")
                    plt.legend()

                    plt.subplot(122)
                    plt.plot(np.array(logger.get_variable_history(2)).flatten(), label="||g||")
                    plt.plot(np.array(logger.get_variable_history(3)).flatten(), label="||g'||")
                    plt.draw()

                trainer.append_task(tasks.Callback(_plot))

        elif args.classification:
            valid_loss = ErrorForSequenceWithClassTarget(model, validset)
            valid_batch_scheduler = SequenceBatchSchedulerWithClassTarget(validset, batch_size=50)
            error = views.LossView(loss=valid_loss, batch_scheduler=valid_batch_scheduler)
            trainer.append_task(tasks.Print("Validset - Error        : {0:.2%} ± {1:.2f}", error.mean, error.stderror))
            lookahead_loss = error.mean

        # Save training progression
        # def save_model(*args):
        def save_model(obj, status):
            print("\n*** Best epoch: {0}".format(obj.best_epoch))
            trainer.save(experiment_path)

        trainer.append_task(stopping_criteria.EarlyStopping(lookahead_loss, lookahead=args.lookahead, eps=args.lookahead_eps, callback=save_model))

        if args.max_epoch is not None:
            trainer.append_task(stopping_criteria.MaxEpochStopping(args.max_epoch))

        trainer.build_theano_graph()

    if resuming:
        with Timer("Loading"):
            trainer.load(experiment_path)

    with Timer("Training"):
        trainer.train()

    trainer.save(experiment_path)
    model.save(experiment_path)

    pickle.dump(logger._history, open(pjoin(experiment_path, "logger.pkl"), 'wb'))

    if args.view:
        import pylab as plt

        # Plot some graphs
        plt.figure()
        plt.subplot(121)
        plt.title("Loss")
        plt.plot(logger.get_variable_history(0), label="Train")
        plt.plot(logger.get_variable_history(1), label="Valid")
        plt.legend()

        plt.subplot(122)
        plt.title("Gradient norm")
        plt.plot(logger.get_variable_history(2), label="||g||")
        plt.show()

if __name__ == "__main__":
    main()




# def learn_direction_and_stopping(args):
#     with Timer("Loading dataset"):
#         trainset, validset, testset = load_ismrm2015_challenge(args.bundles_path)

#         # TODO: do this when generating the data (in the create_dataset script)
#         # Normalize (inplace) the target directions
#         for bundle in trainset.bundles:
#             for target in bundle.targets:
#                 target /= np.sqrt(np.sum(target**2, axis=1, keepdims=True))

#         for target in validset.targets:
#             target /= np.sqrt(np.sum(target**2, axis=1, keepdims=True))

#         # for target in testset.targets:
#         #     target /= np.sqrt(np.sum(target**2, axis=1, keepdims=True))

#         batch_size = 100
#         batch_scheduler = BundlesBatchScheduler(trainset, batch_size, nb_updates_per_epoch=50)

#     with Timer("Creating model"):
#         hidden_size = 100
#         #model = RNN(trainset.input_shape[-1], hidden_size, trainset.target_shape[-1])
#         model = LSTM(trainset.input_shape[-1], hidden_size, trainset.target_shape[-1])
#         model.initialize()  # By default, uniform initialization.

#         save_path = pjoin('experiments', args.name)

#     with Timer("Building optimizer"):
#         #loss = L2DistanceForSequence(model, trainset)
#         #loss = L2DistanceWithBinaryCrossEntropy(model, trainset)
#         loss = L2DistanceWithBinaryCrossEntropy(model, trainset)
#         optimizer = AdaGrad(loss=loss, lr=0.01)

#     with Timer("Building trainer"):
#         trainer = Trainer(optimizer, batch_scheduler)

#         def save_model(*args):
#             model.save(save_path)

#         # Train for 100 epochs
#         trainer.append_task(stopping_criteria.MaxEpochStopping(100))
#         # Add early stopping too
#         error = views.LossView(loss=L2DistanceWithBinaryCrossEntropy(model, validset),
#                                batch_scheduler=SequenceBatchScheduler(validset, batch_size=512))
#         trainer.append_task(stopping_criteria.EarlyStopping(error.mean, lookahead=10, callback=save_model))

#         # Print time for one epoch
#         trainer.append_task(tasks.PrintEpochDuration())
#         trainer.append_task(tasks.PrintTrainingDuration())
#         trainer.append_task(tasks.PrintAverageTrainingLoss(loss))

#         # Print some variables
#         trainer.append_task(tasks.PrintVariable("Avg. Objective: {0}\tCross: {1}",
#                                                 T.mean(loss.mean_sqr_error), T.mean(loss.cross_entropy),
#                                                 ))

#         # Print mean/stderror of loss.
#         trainer.append_task(tasks.Print("Validset - Error: {0:.4f} ± {1:.4f}", error.mean, error.stderror))
#         trainer._build_theano_graph()

#     with Timer("Training"):
#         trainer.train()

#     with Timer("Saving model"):
#         model.save(save_path)