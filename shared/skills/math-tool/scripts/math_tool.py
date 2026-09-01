#!/usr/bin/env python3
"""Bounded symbolic computation for the math-tool skill.

The process accepts JSON only through --request. It never parses mathematical
source text and never evaluates caller-provided Python.
"""

import argparse
import hashlib
import json
import multiprocessing
import os
import re
import sys


PROTOCOL_VERSION = 1
SYMPY_VERSION = "1.14.0"
MPMATH_VERSION = "1.3.0"
OPERATIONS = {
    "differentiate",
    "evaluate",
    "expand",
    "factor",
    "integrate",
    "limit",
    "matrix",
    "simplify",
    "solve",
    "statistics",
}
NODE_TYPES = {
    "add",
    "constant",
    "function",
    "integer",
    "matrix",
    "multiply",
    "power",
    "rational",
    "relation",
    "symbol",
}
FUNCTION_ARITY = {
    "abs": (1, 1),
    "acos": (1, 1),
    "asin": (1, 1),
    "atan": (1, 1),
    "cos": (1, 1),
    "cosh": (1, 1),
    "exp": (1, 1),
    "factorial": (1, 1),
    "gamma": (1, 1),
    "gcd": (2, 16),
    "lcm": (2, 16),
    "log": (1, 2),
    "sin": (1, 1),
    "sinh": (1, 1),
    "sqrt": (1, 1),
    "tan": (1, 1),
    "tanh": (1, 1),
}
CONSTANTS = {"E", "I", "oo", "pi"}
RELATIONS = {"eq", "ge", "gt", "le", "lt", "ne"}
MATRIX_ACTIONS = {"determinant", "inverse", "rank", "rref", "trace", "transpose"}
STATISTICS_ACTIONS = {"mean", "median", "standard_deviation", "variance"}
LIMITS = {
    "request_bytes": 8192,
    "ast_nodes": 256,
    "ast_depth": 24,
    "integer_digits": 1000,
    "symbols": 32,
    "equations": 16,
    "matrix_cells": 256,
    "precision": 100,
    "compute_seconds": 5,
    "result_bytes": 2048,
    "result_tokens": 512,
    "diagnostic_tokens": 96,
}
_SYMBOL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_OBLIGATION_RE = re.compile(r"^[0-9a-f]{32}$")


class MathToolError(Exception):
    """A typed, caller-correctable tool failure."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _require_keys(node, required, optional=()):
    keys = set(node)
    allowed = set(required) | set(optional)
    if not set(required).issubset(keys) or not keys.issubset(allowed):
        raise MathToolError("invalid_ast", "AST node fields are not valid for %s" % node.get("type", "node"))


def _integer_text(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise MathToolError("invalid_integer", "integer values must be decimal integers")
    text = str(value)
    digits = text[1:] if text.startswith("-") else text
    if not digits or not digits.isascii() or not digits.isdigit():
        raise MathToolError("invalid_integer", "integer values must be decimal integers")
    if len(digits) > LIMITS["integer_digits"]:
        raise MathToolError("integer_limit", "integer digit limit exceeded")
    return text


def _symbol_name(value):
    if not isinstance(value, str) or not _SYMBOL_RE.fullmatch(value):
        raise MathToolError("invalid_symbol", "symbol names must be short ASCII identifiers")
    return value


def validate_request(request):
    """Validate the wire request without importing SymPy.

    Return the decoded object. This function is also used by the gate before a
    tool call starts.
    """
    if isinstance(request, str):
        if len(request.encode("utf-8")) > LIMITS["request_bytes"]:
            raise MathToolError("request_limit", "request byte limit exceeded")
        try:
            request = json.loads(request)
        except (ValueError, UnicodeError):
            raise MathToolError("invalid_json", "request must be one JSON object")
    if not isinstance(request, dict):
        raise MathToolError("invalid_request", "request must be one JSON object")
    if len(_json_bytes(request)) > LIMITS["request_bytes"]:
        raise MathToolError("request_limit", "request byte limit exceeded")
    required = {"v", "obligation", "op", "ast"}
    allowed = required | {"variables", "options"}
    if not required.issubset(request) or not set(request).issubset(allowed):
        raise MathToolError("invalid_request", "request fields do not match protocol v1")
    if request.get("v") != PROTOCOL_VERSION:
        raise MathToolError("invalid_version", "request version must be 1")
    if not isinstance(request.get("obligation"), str) or not _OBLIGATION_RE.fullmatch(request["obligation"]):
        raise MathToolError("invalid_obligation", "obligation must be a 32-character lowercase digest")
    operation = request.get("op")
    if operation not in OPERATIONS:
        raise MathToolError("unsupported_operation", "operation is not allowlisted")
    variables = request.get("variables", [])
    if not isinstance(variables, list) or len(variables) > LIMITS["symbols"]:
        raise MathToolError("symbol_limit", "variables must be a bounded list")
    variable_names = [_symbol_name(value) for value in variables]
    if len(variable_names) != len(set(variable_names)):
        raise MathToolError("invalid_variables", "variables must be unique")
    options = request.get("options", {})
    if not isinstance(options, dict):
        raise MathToolError("invalid_options", "options must be one JSON object")

    state = {"nodes": 0, "symbols": set(variable_names), "equations": 0, "matrix_cells": 0}

    def walk(node, depth=1):
        if depth > LIMITS["ast_depth"]:
            raise MathToolError("depth_limit", "AST depth limit exceeded")
        if not isinstance(node, dict):
            raise MathToolError("invalid_ast", "each AST node must be one JSON object")
        kind = node.get("type")
        if kind not in NODE_TYPES:
            raise MathToolError("invalid_ast", "AST node type is not allowlisted")
        # Matrix is a bounded container. Its cell expressions count toward the
        # AST-node ceiling, while the container itself counts toward the
        # separate matrix-cell ceiling. This keeps both published maxima
        # reachable at their exact boundary.
        if kind != "matrix":
            state["nodes"] += 1
            if state["nodes"] > LIMITS["ast_nodes"]:
                raise MathToolError("node_limit", "AST node limit exceeded")
        if kind == "integer":
            _require_keys(node, {"type", "value"})
            _integer_text(node["value"])
        elif kind == "rational":
            _require_keys(node, {"type", "numerator", "denominator"})
            _integer_text(node["numerator"])
            denominator = _integer_text(node["denominator"])
            if int(denominator) == 0:
                raise MathToolError("zero_denominator", "rational denominator must not be zero")
        elif kind == "symbol":
            _require_keys(node, {"type", "name"})
            state["symbols"].add(_symbol_name(node["name"]))
        elif kind == "constant":
            _require_keys(node, {"type", "name"})
            if node["name"] not in CONSTANTS:
                raise MathToolError("invalid_constant", "constant is not allowlisted")
        elif kind in ("add", "multiply"):
            _require_keys(node, {"type", "args"})
            args = node["args"]
            if not isinstance(args, list) or not 2 <= len(args) <= LIMITS["ast_nodes"]:
                raise MathToolError("invalid_ast", "%s requires at least two arguments" % kind)
            for child in args:
                walk(child, depth + 1)
        elif kind == "power":
            _require_keys(node, {"type", "base", "exponent"})
            walk(node["base"], depth + 1)
            walk(node["exponent"], depth + 1)
        elif kind == "function":
            _require_keys(node, {"type", "name", "args"})
            name = node["name"]
            args = node["args"]
            if name not in FUNCTION_ARITY or not isinstance(args, list):
                raise MathToolError("invalid_function", "function is not allowlisted")
            low, high = FUNCTION_ARITY[name]
            if not low <= len(args) <= high:
                raise MathToolError("invalid_function", "function argument count is invalid")
            for child in args:
                walk(child, depth + 1)
        elif kind == "relation":
            _require_keys(node, {"type", "op", "left", "right"})
            if node["op"] not in RELATIONS:
                raise MathToolError("invalid_relation", "relation operator is not allowlisted")
            state["equations"] += 1
            if state["equations"] > LIMITS["equations"]:
                raise MathToolError("equation_limit", "equation limit exceeded")
            walk(node["left"], depth + 1)
            walk(node["right"], depth + 1)
        elif kind == "matrix":
            _require_keys(node, {"type", "rows"})
            rows = node["rows"]
            if not isinstance(rows, list) or not rows or not isinstance(rows[0], list) or not rows[0]:
                raise MathToolError("invalid_matrix", "matrix rows must be a non-empty rectangle")
            width = len(rows[0])
            if any(not isinstance(row, list) or len(row) != width for row in rows):
                raise MathToolError("invalid_matrix", "matrix rows must have equal length")
            state["matrix_cells"] += len(rows) * width
            if state["matrix_cells"] > LIMITS["matrix_cells"]:
                raise MathToolError("matrix_limit", "matrix cell limit exceeded")
            for row in rows:
                for child in row:
                    if isinstance(child, dict) and child.get("type") == "matrix":
                        raise MathToolError("invalid_matrix", "matrix cells cannot contain matrices")
                    walk(child, depth + 1)
        if len(state["symbols"]) > LIMITS["symbols"]:
            raise MathToolError("symbol_limit", "symbol limit exceeded")

    ast = request["ast"]
    if isinstance(ast, list):
        if operation != "solve" or not ast or len(ast) > LIMITS["equations"]:
            raise MathToolError("invalid_ast", "only solve accepts a non-empty relation list")
        for equation in ast:
            walk(equation)
            if equation.get("type") != "relation" or equation.get("op") != "eq":
                raise MathToolError("invalid_equation", "solve lists must contain equality relations")
    else:
        walk(ast)

    precision = options.get("precision")
    if precision is not None and (
        isinstance(precision, bool) or not isinstance(precision, int) or not 1 <= precision <= LIMITS["precision"]
    ):
        raise MathToolError("precision_limit", "precision must be an integer from 1 through 100")
    allowed_options = {"precision"}
    if operation == "differentiate":
        allowed_options.add("orders")
        if not variable_names:
            raise MathToolError("invalid_variables", "differentiate requires variables")
        orders = options.get("orders", [1] * len(variable_names))
        if not isinstance(orders, list) or len(orders) != len(variable_names) or any(
            isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100 for value in orders
        ):
            raise MathToolError("invalid_options", "orders must match variables and contain positive integers")
    elif operation == "integrate":
        allowed_options.add("bounds")
        if not variable_names:
            raise MathToolError("invalid_variables", "integrate requires variables")
        bounds = options.get("bounds", [None] * len(variable_names))
        if not isinstance(bounds, list) or len(bounds) != len(variable_names):
            raise MathToolError("invalid_options", "bounds must match variables")
        for bound in bounds:
            if bound is not None:
                if not isinstance(bound, list) or len(bound) != 2:
                    raise MathToolError("invalid_options", "each bound must be null or [lower, upper]")
                walk(bound[0])
                walk(bound[1])
    elif operation == "limit":
        allowed_options.update({"point", "direction"})
        if len(variable_names) != 1 or "point" not in options:
            raise MathToolError("invalid_options", "limit requires one variable and a point")
        walk(options["point"])
        if options.get("direction", "+-") not in ("+", "-", "+-"):
            raise MathToolError("invalid_options", "limit direction must be +, -, or +-")
    elif operation == "solve":
        if not variable_names:
            raise MathToolError("invalid_variables", "solve requires variables")
    elif operation == "matrix":
        allowed_options.add("action")
        if not isinstance(ast, dict) or ast.get("type") != "matrix" or options.get("action") not in MATRIX_ACTIONS:
            raise MathToolError("invalid_options", "matrix requires a matrix AST and an allowlisted action")
    elif operation == "statistics":
        allowed_options.update({"action", "sample"})
        if not isinstance(ast, dict) or ast.get("type") != "matrix" or options.get("action") not in STATISTICS_ACTIONS:
            raise MathToolError("invalid_options", "statistics requires a matrix AST and an allowlisted action")
        if "sample" in options and not isinstance(options["sample"], bool):
            raise MathToolError("invalid_options", "sample must be boolean")
    if not set(options).issubset(allowed_options):
        raise MathToolError("invalid_options", "operation options are not allowlisted")
    return request


def build_expr(node, sympy_module):
    """Build one SymPy expression from a previously validated typed AST."""
    sp = sympy_module
    kind = node["type"]
    if kind == "integer":
        return sp.Integer(_integer_text(node["value"]))
    if kind == "rational":
        return sp.Rational(_integer_text(node["numerator"]), _integer_text(node["denominator"]))
    if kind == "symbol":
        return sp.Symbol(node["name"])
    if kind == "constant":
        return {"pi": sp.pi, "E": sp.E, "I": sp.I, "oo": sp.oo}[node["name"]]
    if kind == "add":
        return sp.Add(*(build_expr(value, sp) for value in node["args"]))
    if kind == "multiply":
        return sp.Mul(*(build_expr(value, sp) for value in node["args"]))
    if kind == "power":
        return sp.Pow(build_expr(node["base"], sp), build_expr(node["exponent"], sp))
    if kind == "function":
        functions = {
            "abs": sp.Abs,
            "acos": sp.acos,
            "asin": sp.asin,
            "atan": sp.atan,
            "cos": sp.cos,
            "cosh": sp.cosh,
            "exp": sp.exp,
            "factorial": sp.factorial,
            "gamma": sp.gamma,
            "gcd": sp.gcd,
            "lcm": sp.lcm,
            "log": sp.log,
            "sin": sp.sin,
            "sinh": sp.sinh,
            "sqrt": sp.sqrt,
            "tan": sp.tan,
            "tanh": sp.tanh,
        }
        return functions[node["name"]](*(build_expr(value, sp) for value in node["args"]))
    if kind == "relation":
        left = build_expr(node["left"], sp)
        right = build_expr(node["right"], sp)
        relations = {"eq": sp.Eq, "ne": sp.Ne, "lt": sp.Lt, "le": sp.Le, "gt": sp.Gt, "ge": sp.Ge}
        return relations[node["op"]](left, right, evaluate=False)
    if kind == "matrix":
        return sp.Matrix([[build_expr(value, sp) for value in row] for row in node["rows"]])
    raise MathToolError("invalid_ast", "AST node type is not allowlisted")


def _stable_unique(values, sp):
    ordered = sorted(values, key=sp.default_sort_key)
    unique = []
    for value in ordered:
        if not unique or value != unique[-1]:
            unique.append(value)
    return unique


def run_operation(request, sympy_module):
    """Run one allowlisted operation on an already validated request."""
    sp = sympy_module
    operation = request["op"]
    ast = request["ast"]
    expression = [build_expr(value, sp) for value in ast] if isinstance(ast, list) else build_expr(ast, sp)
    variables = [sp.Symbol(name) for name in request.get("variables", [])]
    options = request.get("options", {})
    if operation == "evaluate":
        return sp.simplify(expression.doit())
    if operation == "simplify":
        return sp.simplify(expression)
    if operation == "factor":
        return sp.factor(expression)
    if operation == "expand":
        return sp.expand(expression)
    if operation == "solve":
        equations = expression if isinstance(expression, list) else [expression]
        result = sp.solve(equations, variables, dict=True)
        if isinstance(result, list):
            normalized = []
            seen = set()
            for item in result:
                key = sp.srepr(item)
                if key not in seen:
                    seen.add(key)
                    normalized.append(item)
            result = sorted(normalized, key=lambda value: sp.srepr(value))
        return result
    if operation == "differentiate":
        result = expression
        for variable, order in zip(variables, options.get("orders", [1] * len(variables))):
            result = sp.diff(result, variable, order)
        return result
    if operation == "integrate":
        result = expression
        for variable, bound in zip(variables, options.get("bounds", [None] * len(variables))):
            spec = variable if bound is None else (
                variable,
                build_expr(bound[0], sp),
                build_expr(bound[1], sp),
            )
            result = sp.integrate(result, spec)
        return result
    if operation == "limit":
        return sp.limit(expression, variables[0], build_expr(options["point"], sp), dir=options.get("direction", "+-"))
    if operation == "matrix":
        action = options["action"]
        if action == "determinant":
            return expression.det()
        if action == "inverse":
            return expression.inv()
        if action == "rank":
            return sp.Integer(expression.rank())
        if action == "rref":
            matrix, pivots = expression.rref()
            return {"matrix": matrix, "pivots": tuple(sp.Integer(value) for value in pivots)}
        if action == "trace":
            return expression.trace()
        return expression.T
    if operation == "statistics":
        values = list(expression)
        if not values:
            raise MathToolError("invalid_statistics", "statistics data must not be empty")
        action = options["action"]
        mean = sp.Add(*values) / len(values)
        if action == "mean":
            return sp.simplify(mean)
        if action == "median":
            ordered = sorted(values, key=sp.default_sort_key)
            middle = len(ordered) // 2
            if len(ordered) % 2:
                return ordered[middle]
            return sp.simplify((ordered[middle - 1] + ordered[middle]) / 2)
        denominator = len(values) - (1 if options.get("sample", False) else 0)
        if denominator <= 0:
            raise MathToolError("invalid_statistics", "sample statistics require at least two values")
        variance = sp.simplify(sp.Add(*((value - mean) ** 2 for value in values)) / denominator)
        return variance if action == "variance" else sp.sqrt(variance)
    raise MathToolError("unsupported_operation", "operation is not allowlisted")


def _visible(value, sp):
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda item: sp.sstr(item[0], order="lex"))
        return "{" + ", ".join("%s: %s" % (_visible(key, sp), _visible(item, sp)) for key, item in items) + "}"
    if isinstance(value, (list, tuple)):
        left, right = ("[", "]") if isinstance(value, list) else ("(", ")")
        body = ", ".join(_visible(item, sp) for item in value)
        if isinstance(value, tuple) and len(value) == 1:
            body += ","
        return left + body + right
    return sp.sstr(value, order="lex").replace("\n", " ")


def _approximate(value, precision, sp):
    if isinstance(value, dict):
        return {key: _approximate(item, precision, sp) for key, item in value.items()}
    if isinstance(value, list):
        return [_approximate(item, precision, sp) for item in value]
    if isinstance(value, tuple):
        return tuple(_approximate(item, precision, sp) for item in value)
    if isinstance(value, sp.MatrixBase):
        return value.applyfunc(lambda item: sp.N(item, precision))
    return sp.N(value, precision)


def accepted_result(request, value, sp):
    canonical = _visible(value, sp)
    result = {
        "v": PROTOCOL_VERSION,
        "status": "accepted",
        "obligation": request["obligation"],
        "canonical": canonical,
        "exact": canonical,
    }
    precision = request.get("options", {}).get("precision")
    if precision is not None:
        result["approximate"] = _visible(_approximate(value, precision, sp), sp)
    result["digest"] = hashlib.sha256(_json_bytes(result)).hexdigest()
    return result


def blocked_result(obligation, code, message):
    safe_message = " ".join(str(message).split())[:384]
    return {
        "v": PROTOCOL_VERSION,
        "status": "blocked",
        "obligation": obligation if isinstance(obligation, str) and _OBLIGATION_RE.fullmatch(obligation) else "0" * 32,
        "failure": {"code": str(code)[:64], "message": safe_message},
    }


def serialize_result(result):
    encoded = _json_bytes(result)
    # One UTF-8 byte per token is a conservative upper bound for supported host
    # tokenizers. This also enforces the larger byte ceiling.
    if len(encoded) > LIMITS["result_bytes"] or len(encoded) > LIMITS["result_tokens"]:
        replacement = blocked_result(result.get("obligation"), "result_limit", "result token or byte limit exceeded")
        return _json_bytes(replacement).decode("utf-8"), 2
    return encoded.decode("utf-8"), 0 if result.get("status") == "accepted" else 2


def _runtime_root():
    configured = os.environ.get("MATH_TOOL_RUNTIME_ROOT")
    if configured:
        return os.path.realpath(configured)
    return os.path.realpath(os.path.join(os.path.expanduser("~"), ".cache", "harness", "math-tool"))


def verify_runtime():
    lock_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime.lock.json")
    try:
        with open(lock_path, "rb") as handle:
            lock_bytes = handle.read()
        lock = json.loads(lock_bytes)
        with open(os.path.join(_runtime_root(), "runtime.json"), encoding="utf-8") as handle:
            stamp = json.load(handle)
    except (OSError, ValueError, UnicodeError) as error:
        raise MathToolError("runtime_unavailable", "pinned runtime metadata is unavailable: %s" % type(error).__name__)
    lock_digest = hashlib.sha256(lock_bytes).hexdigest()
    if lock.get("v") != 1 or stamp.get("v") != 1 or stamp.get("lock_digest") != lock_digest:
        raise MathToolError("runtime_mismatch", "runtime lock digest does not match the installed runtime")
    if os.path.realpath(sys.prefix) != os.path.realpath(stamp.get("venv", "")):
        raise MathToolError("runtime_mismatch", "math_tool.py must run with the pinned virtual environment")
    try:
        import mpmath
        import sympy
    except ImportError:
        raise MathToolError("runtime_unavailable", "pinned SymPy packages are unavailable")
    if sympy.__version__ != SYMPY_VERSION or mpmath.__version__ != MPMATH_VERSION:
        raise MathToolError("runtime_mismatch", "pinned SymPy package versions do not match")
    if stamp.get("sympy") != SYMPY_VERSION or stamp.get("mpmath") != MPMATH_VERSION:
        raise MathToolError("runtime_mismatch", "runtime version stamp does not match")
    return sympy


def _worker(request, connection):
    try:
        import sympy

        validated = validate_request(request)
        value = run_operation(validated, sympy)
        connection.send(accepted_result(validated, value, sympy))
    except MathToolError as error:
        connection.send(blocked_result(request.get("obligation") if isinstance(request, dict) else None, error.code, error.message))
    except BaseException as error:
        connection.send(blocked_result(request.get("obligation") if isinstance(request, dict) else None, "compute_failed", type(error).__name__))
    finally:
        connection.close()


def compute_with_timeout(request):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(request, child))
    process.start()
    child.close()
    try:
        if parent.poll(LIMITS["compute_seconds"]):
            result = parent.recv()
        else:
            result = blocked_result(request.get("obligation"), "timeout", "computation exceeded five seconds")
    except (EOFError, OSError):
        result = blocked_result(request.get("obligation"), "compute_failed", "computation process ended without a result")
    finally:
        if process.is_alive():
            process.terminate()
        process.join(1)
        if process.is_alive():
            process.kill()
            process.join(1)
        parent.close()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--request", required=True)
    args = parser.parse_args(argv)
    obligation = None
    try:
        request = validate_request(args.request)
        obligation = request.get("obligation")
        verify_runtime()
        result = compute_with_timeout(request)
    except MathToolError as error:
        result = blocked_result(obligation, error.code, error.message)
    except BaseException as error:
        result = blocked_result(obligation, "internal_error", type(error).__name__)
    output, exit_code = serialize_result(result)
    sys.stdout.write(output + "\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
