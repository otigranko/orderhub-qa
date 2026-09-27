import pytest

from harness import config
from harness.client import MockPartnerClient, OrderHubClient
from harness.robot_sink import RobotSink
from harness.services import Services


# One OrderHub, mock partner API and robot receiver for the whole test run.
@pytest.fixture(scope="session")
def robot():
    sink = RobotSink(config.ROBOT_PORT)
    sink.start()
    yield sink
    sink.stop()


@pytest.fixture(scope="session")
def services(robot):
    s = Services(robot.url)
    s.start()
    yield s
    s.stop()


@pytest.fixture(scope="session")
def hub(services):
    return OrderHubClient()


@pytest.fixture(scope="session")
def partner(services):
    return MockPartnerClient()
