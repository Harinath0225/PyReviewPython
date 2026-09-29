import asyncio
from agent.dependency_flow_subagent import DependencyFlowSubagent

async def main():
    agent = DependencyFlowSubagent(model_name="gemini-3.1-flash-lite")
    diagram = agent.generate_diagram(code_snippet="def add(a,b): return a+b")
    print("DIAGRAM RAW OUTPUT:")
    print(repr(diagram))
    print("---")
    print(diagram)

if __name__ == "__main__":
    asyncio.run(main())
