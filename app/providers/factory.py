from __future__ import annotations

import os

from .base import ResultsProvider
from .json_provider import JsonResultsProvider
from .sample_provider import SampleResultsProvider


def get_results_provider() -> ResultsProvider:
    provider_name = os.getenv('RESULTS_PROVIDER', 'sample').lower()
    if provider_name == 'json':
        return JsonResultsProvider()
    return SampleResultsProvider()
