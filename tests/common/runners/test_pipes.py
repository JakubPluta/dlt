from subprocess import CalledProcessError
import tempfile
from typing import Any, Iterator, NamedTuple
import pytest
from dlt.common.exceptions import UnsupportedProcessStartMethodException

from dlt.common.runners.stdout import iter_stdout, iter_stdout_with_result
from dlt.common.runners.synth_pickle import encode_obj, decode_obj, decode_last_obj
from dlt.common.runners.venv import Venv
from dlt.common.telemetry import TRunMetrics
from dlt.common.utils import digest128b


class _TestPickler(NamedTuple):
    val_str: str
    val_int: int


# this is our unknown NamedTuple
# class _TestPicklex(NamedTuple):
#     val_str: str
#     val_int: int


# class _TestClass:
#     def __init__(self, s1: _TestPicklex, s2: str) -> None:
#         self.s1 = s1
#         self.s2 = s2

class _TestClassUnkField:
    pass
    # def __init__(self, s1: _TestPicklex, s2: str) -> None:
    #     self.s1 = s1
    #     self.s2 = s2


def test_pickle_encoder() -> None:
    obj = [_TestPickler("A", 1), _TestPickler("B", 2), {"C": 3}]
    encoded = encode_obj(obj)
    assert decode_obj(encoded) == obj
    # break the encoding
    assert decode_obj(";" + encoded) is None
    assert decode_obj(digest128b(b"DONT")) is None
    assert decode_obj(digest128b(b"DONT") + "DONT") is None
    # encode unpicklable object
    with open("tests/common/scripts/counter.py", "r", encoding="utf-8") as s:
        assert encode_obj([s]) is None
        with pytest.raises(TypeError):
            assert encode_obj([s], ignore_pickle_errors=False) is None


def test_pickle_encoder_none() -> None:
    assert decode_obj(encode_obj(None)) is None


def test_synth_pickler_unknown_types() -> None:
    # synth unknown tuple
    obj = decode_obj("LfDoYo19lgUOtTn0Ib6JgASVQAAAAAAAAACMH3Rlc3RzLmNvbW1vbi5ydW5uZXJzLnRlc3RfcGlwZXOUjAxfVGVzdFBpY2tsZXiUk5SMA1hZWpRLe4aUgZQu")
    assert type(obj).__name__.endswith("_TestPicklex")
    # this is completely different type
    assert not isinstance(obj, tuple)

    # synth unknown class containing other unknown types
    obj = decode_obj("Koyo502yl4IKMqIxUTJFgASVbQAAAAAAAACMH3Rlc3RzLmNvbW1vbi5ydW5uZXJzLnRlc3RfcGlwZXOUjApfVGVzdENsYXNzlJOUKYGUfZQojAJzMZRoAIwMX1Rlc3RQaWNrbGV4lJOUjAFZlEsXhpSBlIwCczKUjAFVlIwDX3MzlEsDdWIu")
    assert type(obj).__name__.endswith("_TestClass")
    # tuple inside will be synthesized as well
    assert type(obj.s1).__name__.endswith("_TestPicklex")

    # known class containing unknown types
    obj = decode_obj("PozhjHuf2oS7jPcRxKoagASVbQAAAAAAAACMH3Rlc3RzLmNvbW1vbi5ydW5uZXJzLnRlc3RfcGlwZXOUjBJfVGVzdENsYXNzVW5rRmllbGSUk5QpgZR9lCiMAnMxlGgAjAxfVGVzdFBpY2tsZXiUk5SMAVmUSxeGlIGUjAJzMpSMAVWUdWIu")
    assert isinstance(obj, _TestClassUnkField)
    assert type(obj.s1).__name__.endswith("_TestPicklex")

    # commented out code that created encodings
    # print(encode_obj(_TestPicklex("XYZ", 123)))
    # obj = _TestClass(_TestPicklex("Y", 23), "U")
    # obj._s3 = 3
    # print(encode_obj(obj))
    # obj = _TestClassUnkField(_TestPicklex("Y", 23), "U")
    # print(encode_obj(obj))


def test_iter_stdout() -> None:
    with Venv.create(tempfile.mkdtemp()) as venv:
        expected = ["0", "1", "2", "3", "4", "exit"]
        for i, l in enumerate(iter_stdout(venv, "python", "tests/common/scripts/counter.py")):
            assert expected[i] == l
        lines = list(iter_stdout(venv, "python", "tests/common/scripts/empty.py"))
        assert lines == []
        with pytest.raises(CalledProcessError) as cpe:
            list(iter_stdout(venv, "python", "tests/common/scripts/no_stdout_no_stderr_with_fail.py"))
        # empty stdout
        assert cpe.value.output == ""
        assert cpe.value.stderr == ""


def test_iter_stdout_raises() -> None:
    with Venv.create(tempfile.mkdtemp()) as venv:
        expected = ["0", "1", "2"]
        with pytest.raises(CalledProcessError) as cpe:
            for i, l in enumerate(iter_stdout(venv, "python", "tests/common/scripts/raising_counter.py")):
                assert expected[i] == l
        assert cpe.value.returncode == 1
        # the last output line is available
        assert cpe.value.output.strip() == "2"
        # the stderr is available
        assert 'raise Exception("end")' in cpe.value.stderr
        # we actually consumed part of the iterator up until "2"
        assert i == 2
        with pytest.raises(CalledProcessError) as cpe:
            list(iter_stdout(venv, "python", "tests/common/scripts/no_stdout_exception.py"))
        # empty stdout
        assert cpe.value.output == ""
        assert "no stdout" in cpe.value.stderr


def test_stdout_encode_result() -> None:
    # use current venv to execute so we have dlt
    venv = Venv.restore_current()
    lines = list(iter_stdout(venv, "python", "tests/common/scripts/stdout_encode_result.py"))
    # last line contains results
    assert decode_obj(lines[-1]) == ("this is string", TRunMetrics(True, True, 300))

    # stderr will contain pickled exception somewhere
    with pytest.raises(CalledProcessError) as cpe:
        list(iter_stdout(venv, "python", "tests/common/scripts/stdout_encode_exception.py"))
    assert isinstance(decode_last_obj(cpe.value.stderr.split("\n")), Exception)

    # this script returns something that it cannot pickle
    lines = list(iter_stdout(venv, "python", "tests/common/scripts/stdout_encode_unpicklable.py"))
    assert decode_last_obj(lines) is None


def test_iter_stdout_with_result() -> None:
    venv = Venv.restore_current()
    i = iter_stdout_with_result(venv, "python", "tests/common/scripts/stdout_encode_result.py")
    assert iter_until_returns(i) == ("this is string", TRunMetrics(True, True, 300))
    i = iter_stdout_with_result(venv, "python", "tests/common/scripts/stdout_encode_unpicklable.py")
    assert iter_until_returns(i) is None
    # it just excepts without encoding exception
    with pytest.raises(CalledProcessError):
        i = iter_stdout_with_result(venv, "python", "tests/common/scripts/no_stdout_no_stderr_with_fail.py")
        iter_until_returns(i)
    # this raises a decoded exception: UnsupportedProcessStartMethodException
    with pytest.raises(UnsupportedProcessStartMethodException):
        i = iter_stdout_with_result(venv, "python", "tests/common/scripts/stdout_encode_exception.py")
        iter_until_returns(i)


def iter_until_returns(i: Iterator[Any]) -> Any:
    try:
        while True:
            next(i)
    except StopIteration as si:
        return si.value
