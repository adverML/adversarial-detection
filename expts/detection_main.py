"""
Main script for running the adversarial and OOD detection experiments.
"""
from __future__ import absolute_import, division, print_function
import sys
import argparse
import os
import time
import numpy as np
import torch
from torchvision import datasets, transforms
from nets.mnist import *
from nets.svhn import *
from nets.resnet import *
from helpers.constants import *
from helpers.utils import (
    load_model_checkpoint,
    convert_to_loader,
    load_numpy_data,
    get_data_bounds,
    load_adversarial_data,
    load_noisy_data,
    get_path_dr_models,
    get_clean_data_path,
    get_noisy_data_path,
    get_adversarial_data_path,
    get_output_path,
    list_all_adversarial_subdirs,
    check_label_mismatch,
    metrics_varying_positive_class_proportion,
    add_gaussian_noise,
    save_detector_checkpoint,
    load_detector_checkpoint,
    helper_layer_embeddings,
    get_config_trust_score,
    load_adversarial_wrapper
)
from helpers.dimension_reduction_methods import load_dimension_reduction_models
from detectors.detector_odds_are_odd import (
    fit_odds_are_odd,
    detect_odds_are_odd
)
from detectors.deep_mahalanobis import (
    get_mahalanobis_scores,
    fit_mahalanobis_scores,
    get_mahalanobis_labels
)
from detectors.detector_lid_paper import (
    DetectorLID,
    DetectorLIDClassCond,
    DetectorLIDBatch
)
from detectors.detector_proposed import DetectorLayerStatistics
from detectors.detector_deep_knn import DeepKNN
from detectors.detector_trust_score import TrustScore


# Parameters that were used for the attack data generation
ATTACK_PARAMS = {
    'stepsize': 0.05,
    'confidence': 0,
    'epsilon': EPSILON_VALUES[0],
    'maxiterations': 1000,
    'iterations': 40,
    'maxepsilon': 1
}


def main():
    # Training settings
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch-size', type=int, default=256, help='batch size of evaluation')
    parser.add_argument('--model-type', '-m', choices=['mnist', 'cifar10', 'svhn'], default='cifar10',
                        help='model type or name of the dataset')
    parser.add_argument('--detection-method', '--dm', choices=DETECTION_METHODS, default='proposed',
                        help="Detection method to run. Choices are: {}".format(', '.join(DETECTION_METHODS)))
    parser.add_argument('--resume-from-ckpt', action='store_true', default=False,
                        help='Use this option to load results and resume from a previous partially completed run. '
                             'Cross-validation folds that were completed earlier will be skipped in the current run.')
    parser.add_argument('--save-detec-model', action='store_true', default=False,
                        help='Use this option to save the list of detection models from the CV folds to a pickle '
                             'file. Note that the files tend to be large in size.')
    parser.add_argument('--index-adv', type=int, default=0,
                        help='Index of the adversarial attack parameter to use. This indexes the sorted directories '
                             'containing the adversarial data files from different attack parameters.')
    ################ Optional arguments for the proposed method
    parser.add_argument('--test-statistic', '--ts', choices=TEST_STATS_SUPPORTED, default='multinomial',
                        help="Test statistic to calculate at the layers for the proposed method. Choices are: {}".
                        format(', '.join(TEST_STATS_SUPPORTED)))
    parser.add_argument('--score-type', '--st', choices=SCORE_TYPES, default='pvalue',
                        help="Score type to use for the proposed method. Choices are: {}".
                        format(', '.join(SCORE_TYPES)))
    parser.add_argument('--pvalue-fusion', '--pf', choices=['harmonic_mean', 'fisher'], default='harmonic_mean',
                        help="Name of the method to use for combining p-values from multiple layers for the "
                             "proposed method. Choices are: 'harmonic_mean' and 'fisher'")
    parser.add_argument('--ood-detection', '--ood', action='store_true', default=False,
                        help="Option that enables out-of-distribution detection instead of adversarial detection "
                             "for the proposed method")
    parser.add_argument(
        '--use-top-ranked', '--utr', action='store_true', default=False,
        help="Option that enables the proposed method to use only the top-ranked (by p-values) test statistics for "
             "detection. The number of test statistics is specified through the option '--num-layers'"
    )
    parser.add_argument(
        '--use-deep-layers', '--udl', action='store_true', default=False,
        help="Option that enables the proposed method to use only a given number of last few layers of the DNN. "
             "The number of layers is specified through the option '--num-layers'"
    )
    parser.add_argument(
        '--num-layers', '--nl', type=int, default=NUM_TOP_RANKED,
        help="If the option '--use-top-ranked' or '--use-deep-layers' is provided, this option specifies the number "
             "of layers or test statistics to be used by the proposed method"
    )
    parser.add_argument(
        '--combine-classes', '--cc', action='store_true', default=False,
        help="Option that allows low probability classes to be automatically combined into one group for the "
             "multinomial test statistic used with the proposed method"
    )
    ################ Optional arguments for the proposed method
    parser.add_argument('--layer-trust-score', '--lts', choices=LAYERS_TRUST_SCORE, default='input',
                        help="Which layer to use for the trust score calculation. Choices are: {}".
                        format(', '.join(LAYERS_TRUST_SCORE)))
    parser.add_argument('--batch-lid', action='store_true', default=False,
                        help='Use this option to enable batched, faster version of the LID detector')
    parser.add_argument('--num-neighbors', '--nn', type=int, default=-1,
                        help='Number of nearest neighbors (if applicable to the method). By default, this is set '
                             'to be a power of the number of samples (n): n^{:.1f}'.format(NEIGHBORHOOD_CONST))
    parser.add_argument('--modelfile-dim-reduc', '--mdr', default='',
                        help='Path to the saved dimension reduction model file. Specify only if the default path '
                             'needs to be changed.')
    parser.add_argument('--output-dir', '-o', default='', help='directory path for saving the results of detection')
    parser.add_argument('--adv-attack', '--aa', choices=['FGSM', 'PGD', 'CW', CUSTOM_ATTACK], default='PGD',
                        help='type of adversarial attack')
    # parser.add_argument('--p-norm', '-p', choices=['0', '2', 'inf'], default='inf',
    #                     help="p norm for the adversarial attack; options are '0', '2' and 'inf'")
    parser.add_argument('--max-attack-prop', '--map', type=float, default=0.5,
                        help="Maximum proportion of attack samples in the test fold. Should be a value in (0, 1]")
    parser.add_argument('--num-folds', '--nf', type=int, default=CROSS_VAL_SIZE,
                        help='number of cross-validation folds')
    parser.add_argument('--no-cuda', action='store_true', default=False, help='disables CUDA training')
    parser.add_argument('--gpu', type=str, default='0', help='which gpus to execute code on')
    parser.add_argument('--n-jobs', type=int, default=4, help='number of parallel jobs to use for multiprocessing')
    parser.add_argument('--seed', '-s', type=int, default=SEED_DEFAULT, help='seed for random number generation')
    args = parser.parse_args()

    if args.use_top_ranked and args.use_deep_layers:
        raise ValueError("Cannot provide both command line options '--use-top-ranked' and '--use-deep-layers'. "
                         "Specify only one of them.")

    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu
    use_cuda = not args.no_cuda and torch.cuda.is_available()
    device = torch.device("cuda" if use_cuda else "cpu")
    kwargs_loader = {'num_workers': 1, 'pin_memory': True} if use_cuda else {}

    # Number of neighbors
    n_neighbors = args.num_neighbors
    if n_neighbors <= 0:
        n_neighbors = None

    # Output directory
    if not args.output_dir:
        base_dir = get_output_path(args.model_type)
        output_dir = os.path.join(base_dir, 'detection')
    else:
        output_dir = args.output_dir

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    # Method name for results and plots
    method_name = METHOD_NAME_MAP[args.detection_method]

    # Dimensionality reduction to the layer embeddings is applied only for methods in certain configurations
    apply_dim_reduc = False
    if args.detection_method == 'proposed':
        # Name string for the proposed method based on the input configuration
        # Score type suffix in the method name
        st = '{:.4s}'.format(args.score_type)
        if args.score_type == 'pvalue':
            if args.pvalue_fusion == 'harmonic_mean':
                st += '_hmp'
            if args.pvalue_fusion == 'fisher':
                st += '_fis'

        if not args.ood_detection:
            method_name = '{:.5s}_{:.5s}_{}_adv'.format(method_name, args.test_statistic, st)
        else:
            method_name = '{:.5s}_{:.5s}_{}_ood'.format(method_name, args.test_statistic, st)

        if args.use_top_ranked:
            method_name = '{}_top{:d}'.format(method_name, args.num_layers)
        elif args.use_deep_layers:
            method_name = '{}_last{:d}'.format(method_name, args.num_layers)

        # If `n_neighbors` is specified, append that value to the name string
        if n_neighbors is not None:
            method_name = '{}_k{:d}'.format(method_name, n_neighbors)

        apply_dim_reduc = True

    elif args.detection_method == 'trust':
        # Append the layer name to the method name
        method_name = '{:.5s}_{}'.format(method_name, args.layer_trust_score)
        # If `n_neighbors` is specified, append that value to the name string
        if n_neighbors is not None:
            method_name = '{}_k{:d}'.format(method_name, n_neighbors)

        # Dimension reduction is not applied to the logit layer
        if args.layer_trust_score != 'logit':
            apply_dim_reduc = True

    elif args.detection_method == 'dknn':
        apply_dim_reduc = False
        # If `n_neighbors` is specified, append that value to the name string
        if n_neighbors is not None:
            method_name = '{}_k{:d}'.format(method_name, n_neighbors)

    elif args.detection_method in ['lid', 'lid_class_cond']:
        apply_dim_reduc = False
        # If `n_neighbors` is specified, append that value to the name string
        if n_neighbors is not None:
            method_name = '{}_k{:d}'.format(method_name, n_neighbors)

    elif args.detection_method == 'mahalanobis':
        # No dimensionality reduction needed here
        # According to the paper, they internally transform a `C x H x W` layer embedding to a `C x 1` vector
        # through global average pooling
        apply_dim_reduc = False

    # Model file for dimension reduction, if required
    model_dim_reduc = None
    if apply_dim_reduc:
        if args.modelfile_dim_reduc:
            fname = args.modelfile_dim_reduc
        else:
            # Path to the dimension reduction model file
            fname = get_path_dr_models(args.model_type, args.detection_method, test_statistic=args.test_statistic)

        if not os.path.isfile(fname):
            raise ValueError("Model file for dimension reduction is required, but does not exist: {}".format(fname))
        else:
            # Load the dimension reduction models for each layer from the pickle file
            model_dim_reduc = load_dimension_reduction_models(fname)

    config_trust_score = dict()
    if args.detection_method == 'trust':
        # Get the layer index and the layer-specific dimensionality reduction model for the trust score
        config_trust_score = get_config_trust_score(model_dim_reduc, args.layer_trust_score, n_neighbors)

    # Data loader and pre-trained DNN model corresponding to the dataset
    data_path = DATA_PATH
    if args.model_type == 'mnist':
        '''
        transform = transforms.Compose(
            [transforms.ToTensor(),
             transforms.Normalize(*NORMALIZE_IMAGES['mnist'])]
        )
        test_loader = torch.utils.data.DataLoader(
            datasets.MNIST(data_path, train=False, download=True, transform=transform),
            batch_size=args.batch_size, shuffle=True, **kwargs_loader
        )
        '''
        num_classes = 10
        model = MNIST().to(device)
        model = load_model_checkpoint(model, args.model_type)

    elif args.model_type == 'cifar10':
        '''
        transform_test = transforms.Compose(
            [transforms.ToTensor(),
             transforms.Normalize(*NORMALIZE_IMAGES['cifar10'])]
        )
        testset = datasets.CIFAR10(root=data_path, train=False, download=True, transform=transform_test)
        test_loader = torch.utils.data.DataLoader(testset, batch_size=args.batch_size, shuffle=True, **kwargs_loader)
        '''
        num_classes = 10
        model = ResNet34().to(device)
        model = load_model_checkpoint(model, args.model_type)

    elif args.model_type == 'svhn':
        '''
        transform = transforms.Compose(
            [transforms.ToTensor(),
             transforms.Normalize(*NORMALIZE_IMAGES['svhn'])]
        )
        testset = datasets.SVHN(root=data_path, split='test', download=True, transform=transform)
        test_loader = torch.utils.data.DataLoader(testset, batch_size=args.batch_size, shuffle=True, **kwargs_loader)
        '''
        num_classes = 10
        model = SVHN().to(device)
        model = load_model_checkpoint(model, args.model_type)

    else:
        raise ValueError("'{}' is not a valid model type".format(args.model_type))

    # Set model in evaluation mode
    model.eval()

    # Check if the numpy data directory exists
    d = os.path.join(NUMPY_DATA_PATH, args.model_type)
    if not os.path.isdir(d):
        raise ValueError("Directory for the numpy data files not found: {}".format(d))

    # Not used
    attack_params_list = [
        ('stepsize', ATTACK_PARAMS['stepsize']),
        ('confidence', ATTACK_PARAMS['confidence']),
        ('epsilon', ATTACK_PARAMS['epsilon']),
        ('maxiterations', ATTACK_PARAMS['maxiterations']),
        ('iterations', ATTACK_PARAMS['iterations']),
        ('maxepsilon', ATTACK_PARAMS['maxepsilon']),
        ('pnorm', ATTACK_NORM_MAP[args.adv_attack])
    ]

    # Initialization
    if args.resume_from_ckpt:
        scores_folds, labels_folds, models_folds, init_fold = load_detector_checkpoint(output_dir, method_name,
                                                                                       args.save_detec_model)
        print("Loading saved results from a previous run. Completed {:d} fold(s). Resuming from fold {:d}.".
              format(init_fold, init_fold + 1))
    else:
        scores_folds = []
        labels_folds = []
        models_folds = []
        init_fold = 0

    ti = time.time()
    # Cross-validation
    for i in range(init_fold, args.num_folds):
        print("\nProcessing cross-validation fold {:d}:".format(i + 1))
        # Load the saved clean numpy data from this fold
        numpy_save_path = get_clean_data_path(args.model_type, i + 1)
        # Temporary hack to use backup data directory
        # numpy_save_path = numpy_save_path.replace('varun', 'jayaram', 1)
        data_tr, labels_tr, data_te, labels_te = load_numpy_data(numpy_save_path)
        num_clean_tr = labels_tr.shape[0]
        num_clean_te = labels_te.shape[0]
        # Data loader for the train fold
        train_fold_loader = convert_to_loader(data_tr, labels_tr, dtype_x=torch.float, batch_size=args.batch_size,
                                              device=device)
        # Data loader for the test fold
        test_fold_loader = convert_to_loader(data_te, labels_te, dtype_x=torch.float, batch_size=args.batch_size,
                                             device=device)

        # Get the range of values in the data array
        bounds = get_data_bounds(np.concatenate([data_tr, data_te], axis=0))

        print("\nCalculating the layer embeddings and DNN predictions for the clean train data split:")
        layer_embeddings_tr, labels_pred_tr = helper_layer_embeddings(
            model, device, train_fold_loader, args.detection_method, labels_tr
        )
        print("\nCalculating the layer embeddings and DNN predictions for the clean test data split:")
        layer_embeddings_te, labels_pred_te = helper_layer_embeddings(
            model, device, test_fold_loader, args.detection_method, labels_te
        )
        # Delete the data loaders in case they are not used further
        if args.detection_method != 'mahalanobis':
            del train_fold_loader
        if args.detection_method != 'odds':
            del test_fold_loader

        # Load the saved noisy (Gaussian noise) numpy data generated from this training and test fold
        numpy_save_path = get_noisy_data_path(args.model_type, i + 1)
        # Temporary hack to use backup data directory
        # numpy_save_path = numpy_save_path.replace('varun', 'jayaram', 1)
        data_tr_noisy, data_te_noisy = load_noisy_data(numpy_save_path)
        # Noisy data have the same labels as the clean data
        labels_tr_noisy = labels_tr
        labels_te_noisy = labels_te
        # Check the number of noisy samples
        assert data_tr_noisy.shape[0] == num_clean_tr, ("Number of noisy samples from the train fold is different "
                                                        "from expected")
        assert data_te_noisy.shape[0] == num_clean_te, ("Number of noisy samples from the test fold is different "
                                                        "from expected")
        # Data loader for the noisy train and test fold data
        noisy_train_fold_loader = convert_to_loader(data_tr_noisy, labels_tr_noisy, dtype_x=torch.float,
                                                    batch_size=args.batch_size, device=device)
        noisy_test_fold_loader = convert_to_loader(data_te_noisy, labels_te_noisy, dtype_x=torch.float,
                                                   batch_size=args.batch_size, device=device)
        print("\nCalculating the layer embeddings and DNN predictions for the noisy train data split:")
        layer_embeddings_tr_noisy, labels_pred_tr_noisy = helper_layer_embeddings(
            model, device, noisy_train_fold_loader, args.detection_method, labels_tr_noisy
        )
        print("\nCalculating the layer embeddings and DNN predictions for the noisy test data split:")
        layer_embeddings_te_noisy, labels_pred_te_noisy = helper_layer_embeddings(
            model, device, noisy_test_fold_loader, args.detection_method, labels_te_noisy
        )
        # Delete the data loaders in case they are not used further
        del noisy_train_fold_loader
        del noisy_test_fold_loader

        # Load the saved adversarial numpy data generated from this training and test fold
        _, data_te_clean, data_tr_adv, labels_tr_adv, data_te_adv, labels_te_adv = load_adversarial_wrapper(
            i, args.model_type, args.adv_attack, args.max_attack_prop, num_clean_te, index_adv=args.index_adv
        )
        # `labels_te_adv` corresponds to the class labels of the clean samples, not that predicted by the DNN
        labels_te_clean = labels_te_adv

        num_adv_tr = labels_tr_adv.shape[0]
        num_adv_te = labels_te_adv.shape[0]
        print("\nTrain fold: number of clean samples = {:d}, number of adversarial samples = {:d}, % of adversarial "
              "samples = {:.4f}".format(num_clean_tr, num_adv_tr, (100. * num_adv_tr) / (num_clean_tr + num_adv_tr)))
        print("Test fold: number of clean samples = {:d}, number of adversarial samples = {:d}, % of adversarial "
              "samples = {:.4f}".format(num_clean_te, num_adv_te, (100. * num_adv_te) / (num_clean_te + num_adv_te)))

        # Adversarial data loader for the train fold
        adv_train_fold_loader = convert_to_loader(data_tr_adv, labels_tr_adv, dtype_x=torch.float,
                                                  batch_size=args.batch_size, device=device)
        # Adversarial data loader for the test fold
        adv_test_fold_loader = convert_to_loader(data_te_adv, labels_te_adv, dtype_x=torch.float,
                                                 batch_size=args.batch_size, device=device)
        if args.detection_method in ['lid', 'lid_class_cond']:
            # Needed only for the LID method
            print("\nCalculating the layer embeddings and DNN predictions for the adversarial train data split:")
            layer_embeddings_tr_adv, labels_pred_tr_adv = helper_layer_embeddings(
                model, device, adv_train_fold_loader, args.detection_method, labels_tr_adv
            )
            check_label_mismatch(labels_tr_adv, labels_pred_tr_adv)

        print("\nCalculating the layer embeddings and DNN predictions for the adversarial test data split:")
        layer_embeddings_te_adv, labels_pred_te_adv = helper_layer_embeddings(
            model, device, adv_test_fold_loader, args.detection_method, labels_te_adv
        )
        check_label_mismatch(labels_te_adv, labels_pred_te_adv)
        # Delete the data loaders in case they are not used further
        del adv_train_fold_loader
        if args.detection_method != 'odds':
            del adv_test_fold_loader

        # Detection labels (0 denoting clean and 1 adversarial)
        labels_detec = np.concatenate([np.zeros(labels_pred_te.shape[0], dtype=np.int),
                                       np.ones(labels_pred_te_adv.shape[0], dtype=np.int)])
        if args.detection_method == 'odds':
            # call functions from detectors/detector_odds_are_odd.py
            train_inputs = (data_tr, labels_tr)
            # train_adv_inputs = (data_tr_adv, labels_tr_adv)
            predictor = fit_odds_are_odd(train_inputs, 
                                         None, 
                                         model, 
                                         args.model_type, 
                                         num_classes,
                                         bounds[0],
                                         bounds[1])
            next(predictor)
            detections_clean, detections_attack = detect_odds_are_odd(predictor, 
                                                                      test_fold_loader,
                                                                      adv_test_fold_loader,
                                                                      use_cuda=use_cuda)
            scores_adv = np.concatenate([detections_clean, detections_attack])

        elif args.detection_method == 'lid':
            # Set to `None` to skip noisy data
            # layer_embeddings_tr_noisy = None
            kwargs = {
                'n_neighbors': n_neighbors,
                'skip_dim_reduction': (not apply_dim_reduc),
                'model_dim_reduction': model_dim_reduc,
                'max_iter': 200,
                'balanced_classification': True,
                'n_jobs': args.n_jobs,
                'save_knn_indices_to_file': True,
                'seed_rng': args.seed
            }
            if args.batch_lid:
                det_model = DetectorLIDBatch(n_batches=10, **kwargs)
            else:
                det_model = DetectorLID(**kwargs)

            # Fit the detector on clean, noisy, and adversarial data from the training fold
            _ = det_model.fit(layer_embeddings_tr, layer_embeddings_tr_adv,
                              layer_embeddings_noisy=layer_embeddings_tr_noisy)
            # Scores on clean data from the test fold
            scores_adv1 = det_model.score(layer_embeddings_te, cleanup=False)

            # Scores on adversarial data from the test fold
            scores_adv2 = det_model.score(layer_embeddings_te_adv, cleanup=True)

            scores_adv = np.concatenate([scores_adv1, scores_adv2])
            if args.save_detec_model:
                models_folds.append(det_model)

        elif args.detection_method == 'lid_class_cond':
            # Set to `None` to skip noisy data
            # layer_embeddings_tr_noisy = None
            # labels_pred_tr_noisy = None

            det_model = DetectorLIDClassCond(
                n_neighbors=n_neighbors,
                skip_dim_reduction=(not apply_dim_reduc),
                model_dim_reduction=model_dim_reduc,
                max_iter=200,
                balanced_classification=True,
                n_jobs=args.n_jobs,
                save_knn_indices_to_file=True,
                seed_rng=args.seed
            )
            # Fit the detector on clean, noisy, and adversarial data from the training fold
            _ = det_model.fit(layer_embeddings_tr, labels_tr, labels_pred_tr,
                              layer_embeddings_tr_adv, labels_pred_tr_adv,
                              layer_embeddings_noisy=layer_embeddings_tr_noisy,
                              labels_pred_noisy=labels_pred_tr_noisy)
            # Scores on clean data from the test fold
            scores_adv1 = det_model.score(layer_embeddings_te, labels_pred_te, cleanup=False)

            # Scores on adversarial data from the test fold
            scores_adv2 = det_model.score(layer_embeddings_te_adv, labels_pred_te_adv, cleanup=True)

            scores_adv = np.concatenate([scores_adv1, scores_adv2])
            if args.save_detec_model:
                models_folds.append(det_model)

        elif args.detection_method == 'proposed':
            nl = len(layer_embeddings_tr)
            st_ind = 0
            if args.use_deep_layers:
                if args.num_layers > nl:
                    print("WARNING: number of layers specified using the option '--num-layers' exceeds the number "
                          "of layers in the model. Using all the layers.")
                    st_ind = 0
                else:
                    st_ind = nl - args.num_layers
                    print("Using only the last {:d} layer embeddings from the {:d} layers for the proposed method.".
                          format(args.num_layers, nl))

            mod_dr = None if (model_dim_reduc is None) else model_dim_reduc[st_ind:]
            det_model = DetectorLayerStatistics(
                layer_statistic=args.test_statistic,
                score_type=args.score_type,
                ood_detection=args.ood_detection,
                pvalue_fusion=args.pvalue_fusion,
                use_top_ranked=args.use_top_ranked,
                num_top_ranked=args.num_layers,
                skip_dim_reduction=(not apply_dim_reduc),
                model_dim_reduction=mod_dr,
                n_neighbors=n_neighbors,
                n_jobs=args.n_jobs,
                seed_rng=args.seed
            )
            # Fit the detector on clean data from the training fold
            if args.combine_classes and (args.test_statistic == 'multinomial'):
                _ = det_model.fit(layer_embeddings_tr[st_ind:], labels_tr, labels_pred_tr,
                                  combine_low_proba_classes=True)
            else:
                _ = det_model.fit(layer_embeddings_tr[st_ind:], labels_tr, labels_pred_tr)

            # Scores on clean data from the test fold
            scores_adv1 = det_model.score(layer_embeddings_te[st_ind:], labels_pred_te, test_layer_pairs=True)

            # Scores on adversarial data from the test fold
            scores_adv2 = det_model.score(layer_embeddings_te_adv[st_ind:], labels_pred_te_adv, test_layer_pairs=True)

            scores_adv = np.concatenate([scores_adv1, scores_adv2])
            if args.save_detec_model:
                models_folds.append(det_model)

        elif args.detection_method == 'dknn':
            det_model = DeepKNN(
                n_neighbors=n_neighbors,
                skip_dim_reduction=(not apply_dim_reduc),
                model_dim_reduction=model_dim_reduc,
                n_jobs=args.n_jobs,
                seed_rng=args.seed
            )
            # Fit the detector on clean data from the training fold
            _ = det_model.fit(layer_embeddings_tr, labels_tr)

            # Scores on clean data from the test fold
            scores_adv1, labels_pred_dknn1 = det_model.score(layer_embeddings_te)

            # Scores on adversarial data from the test fold
            scores_adv2, labels_pred_dknn2 = det_model.score(layer_embeddings_te_adv)

            scores_adv = np.concatenate([scores_adv1, scores_adv2])
            # labels_pred_dknn = np.concatenate([labels_pred_dknn1, labels_pred_dknn2])
            if args.save_detec_model:
                models_folds.append(det_model)

        elif args.detection_method == 'trust':
            ind_layer = config_trust_score['layer']
            det_model = TrustScore(
                alpha=config_trust_score['alpha'],
                n_neighbors=config_trust_score['n_neighbors'],
                skip_dim_reduction=(not apply_dim_reduc),
                model_dim_reduction=config_trust_score['model_dr'],
                n_jobs=args.n_jobs,
                seed_rng=args.seed
            )
            # Fit the detector on clean data from the training fold
            _ = det_model.fit(layer_embeddings_tr[ind_layer], labels_tr, labels_pred_tr)

            # Scores on clean data from the test fold
            scores_adv1 = det_model.score(layer_embeddings_te[ind_layer], labels_pred_te)

            # Scores on adversarial data from the test fold
            scores_adv2 = det_model.score(layer_embeddings_te_adv[ind_layer], labels_pred_te_adv)

            scores_adv = np.concatenate([scores_adv1, scores_adv2])
            if args.save_detec_model:
                models_folds.append(det_model)

        elif args.detection_method == 'mahalanobis':
            # Sub-directory for this fold so that the output files are not overwritten
            temp_direc = os.path.join(output_dir, 'fold_{}'.format(i + 1))
            if not os.path.isdir(temp_direc):
                os.makedirs(temp_direc)

            # Calculate the mahalanobis distance features per layer and fit a logistic classifier on the extracted
            # features using data from the training fold
            model_detector = fit_mahalanobis_scores(
                model, device, args.adv_attack, args.model_type, num_classes, temp_direc, train_fold_loader,
                data_tr, data_tr_adv, data_tr_noisy, n_jobs=args.n_jobs
            )
            # Calculate the mahalanobis distance features per layer for the best noise magnitude and predict the
            # logistic classifer to score the samples.
            # Scores on clean data from the test fold
            scores_adv1 = get_mahalanobis_scores(model_detector, data_te, model, device, args.model_type)

            # Scores on adversarial data from the test fold
            scores_adv2 = get_mahalanobis_scores(model_detector, data_te_adv, model, device, args.model_type)

            scores_adv = np.concatenate([scores_adv1, scores_adv2])
        else:
            raise ValueError("Unknown detection method name '{}'".format(args.detection_method))

        # Sanity check
        if scores_adv.shape[0] != labels_detec.shape[0]:
            raise ValueError(
                "Detection scores and labels do not have the same length ({:d} != {:d}); method = {}, fold = {:d}".
                    format(scores_adv.shape[0], labels_detec.shape[0], args.detection_method, i + 1)
            )

        scores_folds.append(scores_adv)
        labels_folds.append(labels_detec)
        save_detector_checkpoint(scores_folds, labels_folds, models_folds, output_dir, method_name,
                                 args.save_detec_model)

    print("\nCalculating performance metrics for different proportion of attack samples:")
    fname = os.path.join(output_dir, 'detection_metrics_{}.pkl'.format(method_name))
    results_dict = metrics_varying_positive_class_proportion(
        scores_folds, labels_folds, output_file=fname, max_pos_proportion=args.max_attack_prop, log_scale=False
    )
    print("Performance metrics saved to the file: {}".format(fname))
    tf = time.time()
    print("Total time taken: {:.4f} minutes".format((tf - ti) / 60.))


if __name__ == '__main__':
    main()
