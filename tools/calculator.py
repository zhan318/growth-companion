import ast
import math
import operator
from typing import Any

from tools import registry

# 安全节点白名单
_ALLOWED_NODES = frozenset({
    ast.Expression, ast.Expr, ast.Module,
    ast.Constant,
    ast.BinOp, ast.UnaryOp, ast.Compare,
    ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.FloorDiv, ast.Mod, ast.Pow,
    ast.UAdd, ast.USub,
    ast.BitXor, ast.BitAnd, ast.BitOr, ast.Invert,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Name, ast.Load, ast.Call, ast.keyword,
    ast.IfExp,
    ast.List, ast.Tuple,
})

_SAFE_FUNCS = {
    "abs": abs, "round": round, "int": int, "float": float,
    "min": min, "max": max, "sum": sum, "pow": pow,
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "pi": math.pi, "e": math.e, "log": math.log, "log10": math.log10,
    "exp": math.exp, "ceil": math.ceil, "floor": math.floor,
}

_BINOP_MAP = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow, ast.BitXor: operator.xor,
    ast.BitAnd: operator.and_, ast.BitOr: operator.or_,
}

_UNARYOP_MAP = {
    ast.UAdd: operator.pos, ast.USub: operator.neg,
    ast.Invert: operator.invert,
}

_CMPOP_MAP = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne,
    ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Gt: operator.gt, ast.GtE: operator.ge,
}


class _SafeEvaluator(ast.NodeVisitor):
    """安全表达式求值器。"""

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, (int, float, bool)):
            return node.value
        raise ValueError(f"不支持的常量类型: {type(node.value).__name__}")

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in _SAFE_FUNCS:
            return _SAFE_FUNCS[node.id]
        raise NameError(f"不允许的变量/函数: {node.id}")

    def visit_Call(self, node: ast.Call) -> Any:
        func = self.visit(node.func)
        if func not in _SAFE_FUNCS.values():
            raise ValueError("不允许调用此函数")
        args = [self.visit(a) for a in node.args]
        kwargs = {kw.arg: self.visit(kw.value) for kw in node.keywords if kw.arg}
        return func(*args, **kwargs)

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        left = self.visit(node.left)
        right = self.visit(node.right)
        op_func = _BINOP_MAP.get(type(node.op))
        if op_func is None:
            raise ValueError(f"不支持的二元运算符: {type(node.op).__name__}")
        return op_func(left, right)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = self.visit(node.operand)
        op_func = _UNARYOP_MAP.get(type(node.op))
        if op_func is None:
            raise ValueError(f"不支持的一元运算符: {type(node.op).__name__}")
        return op_func(operand)

    def visit_Compare(self, node: ast.Compare) -> Any:
        left = self.visit(node.left)
        for op, right_node in zip(node.ops, node.comparators, strict=True):
            right = self.visit(right_node)
            op_func = _CMPOP_MAP.get(type(op))
            if op_func is None:
                raise ValueError(f"不支持的比较运算符: {type(op).__name__}")
            result = op_func(left, right)
            if not result and len(node.ops) > 1:
                return False
            left = right
        return result

    def visit_IfExp(self, node: ast.IfExp) -> Any:
        return self.visit(node.body) if self.visit(node.test) else self.visit(node.orelse)

    def visit_List(self, node: ast.List) -> Any:
        return [self.visit(e) for e in node.elts]

    def visit_Tuple(self, node: ast.Tuple) -> Any:
        return tuple(self.visit(e) for e in node.elts)

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Expr(self, node: ast.Expr) -> Any:
        return self.visit(node.value)

    def visit_Module(self, node: ast.Module) -> Any:
        return self.visit(node.body[0]) if node.body else None

    def generic_visit(self, node: ast.AST) -> Any:
        raise ValueError(f"表达式中包含不允许的语法: {type(node).__name__}")

    @classmethod
    def _validate_tree(cls, node: ast.AST):
        if type(node) not in _ALLOWED_NODES:
            raise ValueError(f"不允许的节点类型: {type(node).__name__}")
        for child in ast.iter_child_nodes(node):
            cls._validate_tree(child)


def safe_eval(expression: str) -> Any:
    expression = expression.strip()
    if not expression:
        raise ValueError("表达式不能为空")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"表达式语法错误: {e}") from e
    _SafeEvaluator._validate_tree(tree)
    return _SafeEvaluator().visit(tree)


@registry.register(description="执行数学计算，当用户需要计算加减乘除时调用")
def calculate(expression: str) -> str:
    """安全计算数学表达式，返回人类可读结果。"""
    if not expression or not expression.strip():
        return "表达式不能为空"
    try:
        result = safe_eval(expression)
        formatted = f"{result:g}" if isinstance(result, float) else str(result)
        return f"计算结果：{formatted}"
    except ZeroDivisionError:
        return "错误：除数不能为零"
    except (ValueError, NameError) as e:
        return f"表达式错误：{e}"
    except Exception:
        return "无法计算这个表达式，请检查输入是否正确"
