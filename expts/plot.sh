mdr='./layers_cifar10/models_dimension_reduction.pkl'

# python plot_legend.py -o results_addn

# python plot_layer_stats.py -o "results_addn/layer_stats/FGSM" --aa FGSM --mdr $mdr
# python plot_layer_stats.py -o "results_addn/layer_stats/PGD"  --aa PGD  --mdr $mdr
# python plot_layer_stats.py -o "results_addn/layer_stats/CW"   --aa CW   --mdr $mdr


python generate_plots.py -o "detection/FGSM/outputs_rebel_fisher" -p "results_addn/generate_samples/FGSM/proportion" --x-axis proportion
# python generate_plots.py -o "detection/PGD/outputs_rebel_fisher" -p "results_addn/generate_samples/PGD/proportion" --x-axis proportion
# python generate_plots.py -o "detection/CW/outputs_rebel_fisher"  -p "results_addn/generate_samples/CW/proportion"  --x-axis proportion

# python generate_plots.py -o "detection/FGSM/outputs_rebel_fisher" -p "results_addn/generate_samples/FGSM/norm" --x-axis "norm"
