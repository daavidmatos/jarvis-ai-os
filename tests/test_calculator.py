import pytest
from jarvis.tools.calculator import CalculatorTool

@pytest.mark.asyncio
async def test_calculator():
    r=await CalculatorTool().run(expression="(2+3)*4")
    assert r["result"]==20
