#Detection method
dm='proposed'

#Test statistic
#Options are: 'multinomial', 'binomial', 'trust', 'lid', 'distance'
ts='binomial'

#Scoring method
#Options are: 'pvalue' and 'klpe'
score='pvalue'

#Method for combing p-values from the layers. Applies only if score='pvalue'
#Options are: 'fisher' and 'harmonic_mean'
pf='fisher'

#Dataset
#Options are: 'mnist', 'cifar10', 'svhn'
dataset='cifar10'

#Adversarial attack
#Options are: 'CW', 'PGD', 'FGSM', 'Custom'
attack='PGD'

#Output directory
output_dir='./outputs_rebel_fisher'

#Number of CPU cores
n_jobs=16

#GPU ID
gpu=0

mdr='./layers_cifar10/models_dimension_reduction.pkl'
nf=2

python -u detection_main.py -m $dataset --dm $dm --ts $ts --st $score --pf $pf --adv-attack $attack --gpu $gpu --n-jobs $n_jobs -o $output_dir --mdr $mdr --nf $nf

#Change the p-value fusion method to 'harmonic_mean'
pf='harmonic_mean'

#Output directory
output_dir='./outputs_rebel_hmp'

python -u detection_main.py -m $dataset --dm $dm --ts $ts --st $score --pf $pf --adv-attack $attack --gpu $gpu --n-jobs $n_jobs -o $output_dir --mdr $mdr --nf $nf

#Change the scoring method to 'klpe'
score='klpe'

#Output directory
output_dir='./outputs_rebel_klpe'

python -u detection_main.py -m $dataset --dm $dm --ts $ts --st $score --adv-attack $attack --gpu $gpu --n-jobs $n_jobs -o $output_dir --mdr $mdr --nf $nf