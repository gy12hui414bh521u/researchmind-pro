# test_models.py
from app.models import TaskCreate, TaskStatus, ResearchState, create_initial_state
from app.models import SearchRequest, DocumentIngestURL

def test_models():
    print("开始测试模型...\n")
    
    # 测试 TaskCreate 校验
    task = TaskCreate(query='分析 2025 年大模型竞争格局', depth='deep')
    print(f'✅ TaskCreate: {task.query[:20]}...')
    
    # 测试 ResearchState 初始化
    state = create_initial_state('task-001', 'user-001', task.query)
    print(f'✅ ResearchState: task_id={state["task_id"]}')
    print(f'✅ 初始 iteration_count: {state["iteration_count"]}')
    print(f'✅ 初始 research_results: {state["research_results"]}')
    
    # 测试校验失败
    try:
        bad = TaskCreate(query='ab')   # 太短，应该报错
    except Exception as e:
        print(f'✅ 校验正常拦截短 query: {type(e).__name__}')
    
    print("\n所有模型验证通过")

if __name__ == "__main__":
    test_models()