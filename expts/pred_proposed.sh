#Detection method
dm='proposed'

#Test statistic
#Options are: 'multinomial', 'binomial', 'trust', 'lid', 'distance'
ts='multinomial'

#Scoring method
#Options are: 'pvalue' and 'klpe'
score='pvalue'

#Method for combing p-values from the layers. Applies only if score='pvalue'
#Options are: 'fisher' and 'harmonic_mean'
pf='fisher'

#Dataset
#Options are: 'mnist', 'cifar10', 'svhn'
dataset='cifar10'

#Output directory
output_dir='./outputs_rebel_fisher'



#Number of CPU cores
n_jobs=16

#GPU ID
gpu=0

#Adversarial attack
#Set to  'none' to evaluate on clean data
attack='none'

mdr='./layers_cifar10/models_dimension_reduction.pkl'

nf=2

python -u prediction_main.py -m $dataset --dm $dm --ts $ts --st $score --pf $pf --adv-attack $attack --gpu $gpu --n-jobs $n_jobs -o $output_dir --mdr $mdr --nf $nf

#Evaluate on CW attack with confidence = 0
attack='PGD'
index=0

python -u prediction_main.py -m $dataset --dm $dm --index-adv $index --ts $ts --st $score --pf $pf --adv-attack $attack --gpu $gpu --n-jobs $n_jobs -o $output_dir --mdr $mdr --nf $nf