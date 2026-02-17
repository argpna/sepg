import logging

from sepg import log


class _Capture:
    def __init__(self, level=logging.DEBUG):
        self.level = level
        self.records: list[logging.LogRecord] = []
        self._handler = logging.Handler()
        self._handler.emit = self.records.append
        self._handler.setLevel(level)

    def __enter__(self):
        log.logger.addHandler(self._handler)
        return self.records

    def __exit__(self, *exc):
        log.logger.removeHandler(self._handler)


def test_configure_only_installs_handlers_once():
    before = len(log.logger.handlers)
    log.configure()
    log.configure()
    assert len(log.logger.handlers) == before


def test_configure_does_not_enable_propagation():
    log.configure()
    assert log.logger.propagate is False


def test_step_formats_with_prefix_at_info_level():
    with _Capture() as records:
        log.step("shard", "hello world")

    assert len(records) == 1
    assert records[0].getMessage() == "[shard] hello world"
    assert records[0].levelno == logging.INFO


def test_warn_formats_with_warn_prefix_at_warning_level():
    with _Capture() as records:
        log.warn("something went wrong")

    assert len(records) == 1
    assert records[0].getMessage() == "[warn] something went wrong"
    assert records[0].levelno == logging.WARNING


def test_info_logs_plain_message_at_info_level():
    with _Capture() as records:
        log.info("plain message")

    assert len(records) == 1
    assert records[0].getMessage() == "plain message"
    assert records[0].levelno == logging.INFO


def test_stdout_handler_filter_excludes_warning_and_above():
    stdout_handler = next(h for h in log.logger.handlers if h.stream is __import__("sys").stdout)
    info_record = logging.LogRecord("sepg", logging.INFO, __file__, 0, "x", None, None)
    warning_record = logging.LogRecord("sepg", logging.WARNING, __file__, 0, "x", None, None)

    assert stdout_handler.filter(info_record)
    assert not stdout_handler.filter(warning_record)


def test_stderr_handler_only_emits_warning_and_above():
    stderr_handler = next(h for h in log.logger.handlers if h.stream is __import__("sys").stderr)
    assert stderr_handler.level == logging.WARNING
