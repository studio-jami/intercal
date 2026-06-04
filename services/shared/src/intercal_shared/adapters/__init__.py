"""Concrete adapter implementations for every port.

Each adapter lives in its own module and is selected by the factory based on
the provider setting in `Settings`.  Only the selected adapter's optional
dependency needs to be installed.
"""
