"""测试安全计算器"""
import sys

sys.path.insert(0, "..")

from tools.calculator import calculate


def test_normal_math():
    assert calculate("1+1") == "计算结果：2"
    assert calculate("2*3") == "计算结果：6"
    assert calculate("10/2") == "计算结果：5"
    assert calculate("2**10") == "计算结果：1024"
    assert calculate("(1+2)*3") == "计算结果：9"


def test_functions():
    assert "12" in calculate("sqrt(144)")
    assert "3.14" in calculate("round(3.14159, 2)")
    assert "6.283" in calculate("pi*2")


def test_safety():
    result = calculate("__import__('os').system('dir')")
    assert "错误" in result or "不允许" in result

    result = calculate("open('/etc/passwd')")
    assert "错误" in result or "不允许" in result

    result = calculate("eval('1+1')")
    assert "错误" in result or "不允许" in result


def test_edge_cases():
    assert "不能为空" in calculate("")
    assert "零" in calculate("1/0")
    assert "错误" in calculate("invalid @@@ syntax")
