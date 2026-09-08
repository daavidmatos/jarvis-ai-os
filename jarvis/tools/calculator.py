import ast, operator as op
from jarvis.schemas import RiskLevel
from jarvis.tools.base import Tool

OPS={ast.Add:op.add, ast.Sub:op.sub, ast.Mult:op.mul, ast.Div:op.truediv, ast.Pow:op.pow, ast.Mod:op.mod, ast.USub:op.neg, ast.UAdd:op.pos}

def _eval(node):
    if isinstance(node, ast.Expression): return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value,(int,float)): return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in OPS: return OPS[type(node.op)](_eval(node.left),_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS: return OPS[type(node.op)](_eval(node.operand))
    raise ValueError("Unsupported expression")

class CalculatorTool(Tool):
    name="calculator"; description="Evaluate a safe arithmetic expression."; risk=RiskLevel.LOW
    async def run(self, expression: str):
        tree=ast.parse(expression,mode="eval")
        return {"expression":expression,"result":_eval(tree)}
