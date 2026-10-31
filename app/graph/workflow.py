"""
LangGraph 工作流定义模块
组装完整的 AI 内容运营工作流

LangGraph 1.0+ 语法
"""
from typing import Literal
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command

from app.graph.state import AgentState
from app.graph.nodes import (
    write_draft_node,
    extract_visuals_node,
    generate_images_node,
)
from app.graph.utils import get_checkpointer
from app.graph.subgraphs.topic_selection import get_compiled_topic_selection_subgraph


async def human_review_node(state: AgentState) -> Command[Literal["extract_visuals", "write_draft"]]:
    """
    人工审稿节点 (使用 LangGraph 1.0+ interrupt 模式)
    
    使用 interrupt() 暂停执行，等待人工审核
    
    Args:
        state: 当前工作流状态
        
    Returns:
        Command 对象，根据审核结果决定下一步
    """
    article_content = state.get("article_content", "")
    
    # 使用 interrupt 暂停，等待用户审核
    user_input = interrupt({
        "message": "请审核以下文章内容",
        "article_preview": article_content[:500] + "..." if len(article_content) > 500 else article_content,
        "action_required": "review",
        "options": ["approve", "reject"]
    })
    
    # 解析用户的审核结果
    if isinstance(user_input, dict):
        action = user_input.get("action", "reject")
        feedback = user_input.get("feedback", "")
    else:
        action = "reject"
        feedback = ""
    
    if action == "approve":
        return Command(
            update={
                "review_status": "approved",
                "review_feedback": "",
                "status": "review_approved",
            },
            goto="extract_visuals"
        )
    else:
        return Command(
            update={
                "review_status": "rejected",
                "review_feedback": feedback,
                "status": "review_rejected",
            },
            goto="write_draft"
        )


def build_workflow_graph() -> StateGraph:
    """
    构建工作流图 (LangGraph 1.0+ 语法)
    
    工作流逻辑：
    1. Start -> topic_selection (选题子图：AI 生成选题 + 人工选题)
    2. topic_selection -> write_draft (AI 写文章)
    3. INTERRUPT: human_review (等待人工审稿，使用 interrupt())
    4. human_review -> 条件路由:
       - approved: extract_visuals -> generate_images -> End
       - rejected: 回到 write_draft (重写)
    
    Returns:
        StateGraph 实例
    """
    # 创建状态图
    workflow = StateGraph(AgentState)
    
    # 获取编译后的选题子图
    topic_selection_subgraph = get_compiled_topic_selection_subgraph()
    
    # 添加节点
    # 使用子图作为节点：将选题相关逻辑封装为 topic_selection 子图
    workflow.add_node("topic_selection", topic_selection_subgraph)
    workflow.add_node("write_draft", write_draft_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("extract_visuals", extract_visuals_node)
    workflow.add_node("generate_images", generate_images_node)
    
    # 添加边
    # Start -> topic_selection (选题子图)
    workflow.add_edge(START, "topic_selection")
    
    # topic_selection -> write_draft (子图完成后进入写作)
    workflow.add_edge("topic_selection", "write_draft")
    
    # write_draft -> human_review
    workflow.add_edge("write_draft", "human_review")
    
    # human_review 使用 Command 动态路由 (approved -> extract_visuals, rejected -> write_draft)
    
    # extract_visuals -> generate_images
    workflow.add_edge("extract_visuals", "generate_images")
    
    # generate_images -> End
    workflow.add_edge("generate_images", END)
    
    return workflow


async def get_compiled_graph():
    """
    获取编译后的工作流图（带持久化）
    
    LangGraph 1.0+ 使用 interrupt() 函数实现中断，
    不再需要 interrupt_before 参数
    
    Returns:
        编译后的 CompiledStateGraph 实例
    """
    # 获取 Checkpointer
    checkpointer = await get_checkpointer()
    
    # 构建工作流图
    workflow = build_workflow_graph()
    
    # 编译图，配置持久化
    # LangGraph 1.0+ 中断由 interrupt() 函数控制，不需要 interrupt_before
    compiled_graph = workflow.compile(
        checkpointer=checkpointer,
    )
    
    return compiled_graph


# 用于存储编译后的图实例
_compiled_graph = None


async def get_graph():
    """
    获取或创建编译后的图实例（单例模式）
    
    Returns:
        编译后的 CompiledStateGraph 实例
    """
    global _compiled_graph
    
    if _compiled_graph is None:
        _compiled_graph = await get_compiled_graph()
    
    return _compiled_graph


async def reset_graph():
    """
    重置图实例（用于重新初始化）
    """
    global _compiled_graph
    _compiled_graph = None
