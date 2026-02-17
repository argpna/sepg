import logging
import sys

logger = logging.getLogger("sepg")
_configured = False


def configure(level: int = logging.INFO) -> None:
    """Attach stdout/stderr handlers with timestamps; safe to call repeatedly (e.g. once per
    multiprocessing worker) - only the first call installs handlers, later calls just adjust level."""
    global _configured

    logger.setLevel(level)
    if _configured:
        return

    fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(fmt)
    stdout_handler.addFilter(lambda record: record.levelno < logging.WARNING)
    logger.addHandler(stdout_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(fmt)
    stderr_handler.setLevel(logging.WARNING)
    logger.addHandler(stderr_handler)

    logger.propagate = False
    _configured = True


configure()


def info(msg: str) -> None:
    logger.info(msg)


def step(prefix: str, msg: str) -> None:
    logger.info("[%s] %s", prefix, msg)


def warn(msg: str) -> None:
    logger.warning("[warn] %s", msg)
