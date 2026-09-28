import pytest

from harness import config
from harness.client import MockPartnerClient, OrderHubClient
from harness.robot_sink import RobotSink
from harness.services import Services, is_up


# One OrderHub, mock partner API and robot receiver for the whole test run.
# With QA_EXTERNAL=1 only the robot receiver is started; OrderHub is the one you are running.
@pytest.fixture(scope="session")
def robot():
    sink = RobotSink(config.ROBOT_PORT)
    sink.start()
    yield sink
    sink.stop()


@pytest.fixture(scope="session")
def services(robot):
    if config.EXTERNAL:
        if not is_up(f"{config.ORDERHUB_URL}/healthz"):
            pytest.exit(f"QA_EXTERNAL=1 but OrderHub is not running at {config.ORDERHUB_URL}. "
                        f"Start it with: ORDERHUB_ROBOT_URL={robot.url} make run", returncode=2)
        yield None
        return

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
