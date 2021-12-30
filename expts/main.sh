#!/bin/bash

# conda create -n detect python=3.6 
# conda env update --file conda_pynndescent.yml

# ResolvePackageNotFound: 
#   - appnope=0.1.0
#   - libgfortran=3.0.1

# conda install appnope libgfortran

# Traceback (most recent call last):
#   File "layers.py", line 10, in <module>
#     import torch
# ModuleNotFoundError: No module named 'torch'

# conda install pytorch torchvision -c pytorch
# pip install foolbox
# conda install pympler
# conda install scikit-learn==0.20.3
# conda install -c conda-forge pynndescent
# conda install matplotlib==3.0.3

# conda install numpy==1.16.2 scipy==1.2.1 joblib==0.14.0 scikit-learn==0.20.3 numba==0.46.0 llvmlite==0.30.0 pynndescent==0.3.3  matplotlib==3.0.3

# cd expts
# python generate_samples.py --tb 1000 --gpu 0 --nf 2 --aa FGSM
#  python generate_samples.py --tb 1000 --gpu 0 --nf 2 --aa CW -p 2
# python generate_noisy_data.py --tb 1000 --gpu 0 --nf 2   --search-noise-stdev
# python layers.py -b 256 -o "layers_cifar10" --n-jobs 4


# python generate_samples.py --tb 1000 --gpu 0  --nf 3 --aa FGSM
python generate_samples.py --tb 1000 --gpu 0 --epsilon 0.03 --max-epsilon 0.03 --nf 3 --aa FGSM

# python generate_samples.py --tb 1000 --gpu 0 --max-epsilon 0.3 --nf 3 --aa PGD
# python generate_samples.py --tb 1000 --gpu 0 --nf 3 --max-epsilon 0.3 --aa CW  -p 2

