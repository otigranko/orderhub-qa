import pytest

from harness.client import MockPartnerClient, OrderHubClient


@pytest.fixture(scope="session")
def hub():
    return OrderHubClient()


@pytest.fixture(scope="session")
def partner():
    return MockPartnerClient()
