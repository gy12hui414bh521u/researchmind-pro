# test_graph.py
from app.agents.graph import build_graph
from langgraph.checkpoint.memory import MemorySaver

def test_graph():
    print("测试构建 Graph...")
    
    # 构建 Graph（不需要数据库）
    graph = build_graph(MemorySaver())
    print('✅ Graph 构建成功')
    
    # 打印节点结构
    nodes = list(graph.nodes.keys())
    print(f'✅ 节点: {nodes}')
    
    # 可选：打印边结构
    print("\n详细结构:")
    print(f"节点列表: {nodes}")
    for node in nodes:
        if node != '__start__':
            print(f"  - {node}")
    
    # 获取起始节点
    start_node = graph.get_node('__start__')
    print(f"\n起始节点: {start_node}")

if __name__ == "__main__":
    test_graph()