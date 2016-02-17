# Copyright 2016 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Statistical hypothesis testing for comparing benchmark results."""

try:
  from scipy import stats
  import scipy.version
except ImportError:
  stats = None


MANN = 'mann'
KOLMOGOROV = 'kolmogorov'
WELCH = 'welch'
ALL_TEST_OPTIONS = [MANN, KOLMOGOROV, WELCH]


class DictMismatchError(Exception):
  """Provides exception for result dicts with mismatching keys/metrics."""
  def __str__(self):
    return ("Provided benchmark result dicts' keys/metrics do not match. "
            "Check if they have been created by the same benchmark.")


class SampleSizeError(Exception):
  """Provides exception for sample sizes too small for Mann-Whitney U-test."""
  def __str__(self):
    return ('At least one sample size is smaller than 20, which is too small '
            'for Mann-Whitney U-test.')


class NonNormalSampleError(Exception):
  """Provides exception for samples that are not normally distributed."""
  def __str__(self):
    return ("At least one sample is not normally distributed as required by "
            "Welch's t-test.")


def IsScipyMannTestOneSided():
  """Checks if Scipy version is < 0.17.0.

  This is the version where stats.mannwhitneyu(...) is changed from returning
  a one-sided to returning a two-sided p-value.
  """
  scipy_version = [int(num) for num in scipy.version.version.split('.')]
  return scipy_version[0] < 1 and scipy_version[1] < 17


def CreateBenchmarkResultDict(benchmark_result_json):
  """Creates a dict of format {measure_name: list of benchmark results}.

  Takes a raw result Chart-JSON produced when using '--output-format=chartjson'
  when running 'run_benchmark'.

  Args:
    benchmark_result_json: Benchmark result Chart-JSON produced by Telemetry.

  Returns:
    Dictionary of benchmark results.
    Example dict entry: 'first_main_frame_load_time': [650, 700, ...].
  """
  try:
    charts = benchmark_result_json['charts']
  except KeyError:
    raise ValueError('Invalid benchmark result format. Make sure input is a '
                     'Chart-JSON.\nProvided JSON:\n',
                     repr(benchmark_result_json))

  benchmark_result_dict = {}
  for elem_name, elem_content in charts.iteritems():
    benchmark_result_dict[elem_name] = elem_content['summary']['values']

  return benchmark_result_dict


def IsNormallyDistributed(sample, significance_level=0.05):
  """Calculates Shapiro-Wilk test for normality for a single sample.

  Note that normality is a requirement for Welch's t-test.

  Args:
    sample: List of values.
    significance_level: The significance level the p-value is compared against.

  Returns:
    is_normally_distributed: Returns True or False.
    p_value: The calculated p-value.
  """
  if not stats:
    raise ImportError('This function requires Scipy.')

  # pylint: disable=unbalanced-tuple-unpacking
  _, p_value = stats.shapiro(sample)

  is_normally_distributed = p_value >= significance_level
  return is_normally_distributed, p_value


def AreSamplesDifferent(sample_1, sample_2, test=MANN,
                        significance_level=0.05):
  """Calculates the specified statistical test for the given samples.

  The null hypothesis for each test is that the two populations that the
  samples are taken from are not significantly different. Tests are two-tailed.

  Raises:
    ImportError: Scipy is not installed.
    SampleSizeError: Sample size is too small for MANN.
    NonNormalSampleError: Sample is not normally distributed as required by
    WELCH.

  Args:
    sample_1: First list of values.
    sample_2: Second list of values.
    test: Statistical test that is used.
    significance_level: The significance level the p-value is compared against.

  Returns:
    is_different: True or False, depending on the test outcome.
    p_value: The p-value the test has produced.
  """
  if not stats:
    raise ImportError('This function requires Scipy.')

  if test == MANN:
    if len(sample_1) < 20 or len(sample_2) < 20:
      raise SampleSizeError()
    _, p_value = stats.mannwhitneyu(sample_1, sample_2, use_continuity=True)
    if IsScipyMannTestOneSided():
      p_value = p_value * 2 if p_value < 0.5 else 1

  elif test == KOLMOGOROV:
    _, p_value = stats.ks_2samp(sample_1, sample_2)

  elif test == WELCH:
    if not (IsNormallyDistributed(sample_1, significance_level)[0] and
            IsNormallyDistributed(sample_2, significance_level)[0]):
      raise NonNormalSampleError()
    _, p_value = stats.ttest_ind(sample_1, sample_2, equal_var=False)
  # TODO: Add k sample anderson darling test

  is_different = p_value <= significance_level
  return is_different, p_value


def AreBenchmarkResultsDifferent(result_dict_1, result_dict_2, test=MANN,
                                 significance_level=0.05):
  """Runs the given test on the results of each metric in the benchmarks.

  Checks if the dicts have been created from the same benchmark, i.e. if
  metric names match (e.g. first_non_empty_paint_time). Then runs the specified
  statistical test on each metric's samples to find if they vary significantly.

  Args:
    result_dict_1: Benchmark result dict of format {metric: list of values}.
    result_dict_2: Benchmark result dict of format {metric: list of values}.
    test: Statistical test that is used.
    significance_level: The significance level the p-value is compared against.

  Returns:
    test_outcome_dict: Format {metric: (bool is_different, p-value)}.
  """
  if result_dict_1.viewkeys() != result_dict_2.viewkeys():
    raise DictMismatchError()

  test_outcome_dict = {}
  for metric in result_dict_1:
    is_different, p_value = AreSamplesDifferent(result_dict_1[metric],
                                                result_dict_2[metric],
                                                test, significance_level)
    test_outcome_dict[metric] = (is_different, p_value)

  return test_outcome_dict
