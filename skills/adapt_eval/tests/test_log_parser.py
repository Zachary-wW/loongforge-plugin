import importlib.util
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).parent.parent / "scripts"
_SPEC = importlib.util.spec_from_file_location("log_parser", _SCRIPTS / "log_parser.py")
log_parser = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(log_parser)


def test_extract_lm_loss_basic():
    text = (
        " iteration       1/    10 | lm loss: 1.024681E+01 | grad norm: 0.5\n"
        " iteration       2/    10 | lm loss: 9.871234E+00 | grad norm: 0.4\n"
    )
    losses = log_parser.extract_losses(text, max_steps=10)
    assert len(losses) == 2
    assert losses[0] == pytest.approx(10.24681)
    assert losses[1] == pytest.approx(9.871234)


def test_extract_lm_loss_truncates_to_max_steps():
    text = "\n".join(
        f" iteration       {i}/   100 | lm loss: {i}.0E+00 |" for i in range(1, 21)
    )
    losses = log_parser.extract_losses(text, max_steps=10)
    assert len(losses) == 10
    assert losses[0] == pytest.approx(1.0)
    assert losses[9] == pytest.approx(10.0)


def test_extract_lm_loss_returns_empty_on_no_match():
    text = "starting training\nrandom non-loss output\n"
    assert log_parser.extract_losses(text, max_steps=10) == []


def test_extract_lm_loss_handles_decimal_form():
    text = " iteration       1/   10 | lm loss: 2.7183 | grad norm: 0.5\n"
    losses = log_parser.extract_losses(text, max_steps=10)
    assert losses == [pytest.approx(2.7183)]


def test_extract_lm_loss_strips_ansi_color_codes():
    text = " iteration       1/   10 | lm loss: \x1b[33m1.024681E+01\x1b[0m | grad norm: 0.5\n"
    losses = log_parser.extract_losses(text, max_steps=10)
    assert losses == [pytest.approx(10.24681)]
