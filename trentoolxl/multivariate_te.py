import numpy as np
import nonuniform_embedding as nu
from set_estimator import Estimator_cmi

# idea: have a data matrix, use indices to access data, i.e., (a,b,c), where a
# is the time series, b is point in time, c is trial
# is passing indices and ALL data more expensive than cutting and passing data?


def multivariate_te(source_set, target, delta_min, delta_max, cmi_estimator_name):

    """ Find the effective network for the given source and target processes. 
    
    Uses non uniform embedding as proposed by Faes and the algorithm proposed by 
    Lizier.
    """
    
    cmi_estimator = Estimator_cmi(cmi_estimator)

    # find embedding, first for target then for sources
    idx_current_value = delta_max
    idx_candidate_set_target = np.arange(idx_current_value)
    idx_candidate_set_source = np.arange(idx_current_value - delta_min + 1)
    embedding_target = nu.nonuniform_embedding(target, idx_current_value,
                                               idx_candidate_set_target)
    embedding_source = nu.nonuniform_embedding(source_set, idx_current_value,
                                               idx_candidate_set_source,
                                               embedding_target)

    # additiional pruning step
    for candidate in conditional:
        realisations_current_candidate = get_realisations.single_process(data[candidate[0]], candidate[1])
        current_conditional = set_operations.substraction(conditional, candidate)
        realisations_current_conditional = get_realisations.set(data, current_conditional)
        temp_cmi = cmi_estimator.estimate(realisations_current_value, realisations_current_candidate, realisations_current_conditional)
        significant = maximum_statistic(data, conditional, max_cmi)

        if not significant:
            conditional = current_conditional

if __name__ == "__main__":
    n_samples = 1000
    n_sources = 5
    n_trials = 10
    target = np.random.randn(1, n_samples, n_trials)
    source_set = np.random.randn(n_sources, n_samples, n_trials)
    delta_max = 10
    delta_min = 5
    cmi_estimator = 'jidt_kraskov'
    multivariate_te(source_set, target, delta_min, delta_max, cmi_estimator)
