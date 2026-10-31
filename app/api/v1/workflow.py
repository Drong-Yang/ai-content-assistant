"""
工作流 API 接口模块
提供启动、查看状态、恢复运行等核心接口
支持SSE流式输出

LangGraph 1.0+ 语法：使用 Command 模式恢复中断的工作流
"""
import uuid
import json
from typing import Optional, Dict, Any, List, Literal, AsyncGenerator
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from langgraph.types import Command
import psycopg

from app.graph.workflow import get_graph
from app.graph.state import INITIAL_STATE
from app.graph.utils import get_checkpointer
from app.core.config import settings
from app.core.logger import app_logger
from app.models.user import User
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/workflow", tags=["Workflow"])


# ============== 请求/响应模型 ==============

class NodeMetricInfo(BaseModel):
    """节点执行指标"""
    node_name: str = Field(..., description="节点名称")
    duration_ms: float = Field(default=0, description="执行耗时(毫秒)")
    input_tokens: int = Field(default=0, description="输入token数量")
    output_tokens: int = Field(default=0, description="输出token数量")
    total_tokens: int = Field(default=0, description="总token数量")
    start_time: str = Field(default="", description="开始时间")
    end_time: str = Field(default="", description="结束时间")
    model: str = Field(default="", description="使用的模型")


class StartWorkflowRequest(BaseModel):
    """启动工作流请求"""
    topic_direction: str = Field(
        ..., 
        description="主题方向，例如：AI技术、Python开发",
        min_length=1,
        max_length=200
    )


class StartWorkflowResponse(BaseModel):
    """启动工作流响应"""
    thread_id: str = Field(..., description="工作流线程ID")
    status: str = Field(..., description="当前状态")
    generated_topics: List[str] = Field(default=[], description="生成的选题标题列表")
    message: str = Field(..., description="提示信息")
    interrupt_info: Optional[Dict[str, Any]] = Field(default=None, description="中断信息")
    node_metrics: List[NodeMetricInfo] = Field(default=[], description="节点执行指标")


class WorkflowStateResponse(BaseModel):
    """工作流状态响应"""
    thread_id: str = Field(..., description="工作流线程ID")
    status: str = Field(..., description="当前状态")
    values: Dict[str, Any] = Field(default={}, description="当前状态值")
    next_nodes: List[str] = Field(default=[], description="下一个待执行节点")
    is_completed: bool = Field(default=False, description="是否已完成")
    interrupt_info: Optional[Dict[str, Any]] = Field(default=None, description="中断信息")
    node_metrics: List[NodeMetricInfo] = Field(default=[], description="节点执行指标")


class ResumeWorkflowRequest(BaseModel):
    """恢复工作流请求"""
    action: Literal["select_topic", "approve", "reject"] = Field(
        ..., 
        description="操作类型：select_topic(选择选题)、approve(通过审核)、reject(驳回)"
    )
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="操作数据，select_topic时需要selected_topic，reject时需要feedback"
    )


class ResumeWorkflowResponse(BaseModel):
    """恢复工作流响应"""
    thread_id: str = Field(..., description="工作流线程ID")
    status: str = Field(..., description="当前状态")
    message: str = Field(..., description="提示信息")
    next_nodes: List[str] = Field(default=[], description="下一个待执行节点")
    is_completed: bool = Field(default=False, description="是否已完成")
    result: Optional[Dict[str, Any]] = Field(default=None, description="完成时的结果")
    interrupt_info: Optional[Dict[str, Any]] = Field(default=None, description="下一个中断信息")
    node_metrics: List[NodeMetricInfo] = Field(default=[], description="节点执行指标")


class ThreadInfo(BaseModel):
    """线程信息"""
    thread_id: str = Field(..., description="线程ID")
    topic_direction: str = Field(default="", description="主题方向")
    selected_topic: str = Field(default="", description="选中的选题")
    status: str = Field(default="", description="当前状态")
    is_completed: bool = Field(default=False, description="是否已完成")
    created_at: Optional[str] = Field(default=None, description="创建时间")


class ThreadListResponse(BaseModel):
    """线程列表响应"""
    threads: List[ThreadInfo] = Field(default=[], description="线程列表")
    total: int = Field(default=0, description="总数")


# ============== 辅助函数 ==============

def extract_interrupt_info(state_snapshot) -> Optional[Dict[str, Any]]:
    """
    从状态快照中提取中断信息
    
    LangGraph 1.0+ 的中断信息存储在 tasks 中
    """
    if not state_snapshot or not hasattr(state_snapshot, 'tasks'):
        return None
    
    for task in state_snapshot.tasks:
        if hasattr(task, 'interrupts') and task.interrupts:
            for interrupt_obj in task.interrupts:
                if hasattr(interrupt_obj, 'value'):
                    return interrupt_obj.value
    
    return None


def public_values(snapshot):
    """Read the paused subgraph state without mutating parent checkpoints."""
    values = dict(snapshot.values or {})
    for task in snapshot.tasks or ():
        child = getattr(task, "state", None)
        if hasattr(child, "values") and not callable(child.values):
            values.update(public_values(child))
        if getattr(task, "error", None):
            values["status"] = "node_failed"
            values["error"] = "生成步骤失败，请检查配置后重试。"
    info = extract_interrupt_info(snapshot)
    if info and info.get("action_required") == "select_topic":
        values["generated_topics"] = info.get("options", [])
        values["status"] = "topics_generated"
    return values


def validate_resume(snapshot, action, data):
    if snapshot is None or not snapshot.values:
        raise HTTPException(404, "未找到工作流")
    info = extract_interrupt_info(snapshot)
    expected = "select_topic" if action == "select_topic" else "review"
    if not info or info.get("action_required") != expected:
        raise HTTPException(409, "当前阶段不支持此操作，请刷新状态")
    if action == "select_topic" and (not data or data.get("selected_topic") not in public_values(snapshot).get("generated_topics", [])):
        raise HTTPException(400, "请选择本工作流生成的有效选题")


# ============== API 接口 ==============

@router.post("/start", response_model=StartWorkflowResponse)
async def start_workflow(
    request: StartWorkflowRequest,
    current_user: User = Depends(get_current_user)
) -> StartWorkflowResponse:
    """
    启动新的工作流（选题阶段：非流式 + 结构化输出 + token统计）
    
    接收主题方向，启动工作流并运行到第一个中断点（选题阶段）
    返回生成的5个选题标题
    
    Args:
        request: 包含 topic_direction 的请求体
        
    Returns:
        包含 thread_id 和生成的选题列表
    """
    try:
        # 生成唯一的线程 ID（包含用户ID前缀用于隔离）
        thread_id = f"{current_user.id}_{uuid.uuid4()}"
        
        # 记录工作流启动
        app_logger.workflow_started(
            thread_id=thread_id,
            topic_direction=request.topic_direction
        )
        
        # 获取编译后的图
        graph = await get_graph()
        
        # 配置
        config = {"configurable": {"thread_id": thread_id}}
        
        # 初始输入
        initial_input = {
            **INITIAL_STATE,
            "topic_direction": request.topic_direction,
            "status": "started",
        }
        
        # 运行图直到第一个中断点
        # LangGraph 1.0+ 中 ainvoke 会在遇到 interrupt() 时暂停
        result = await graph.ainvoke(initial_input, config)
        
        # 获取状态快照以获取中断信息
        state_snapshot = await graph.aget_state(config, subgraphs=True)
        interrupt_info = extract_interrupt_info(state_snapshot)
        
        result = public_values(state_snapshot)

        # 获取生成的选题
        generated_topics = result.get("generated_topics", [])
        current_status = result.get("status", "unknown")
        node_metrics = result.get("node_metrics", [])
        
        # 记录阶段变化
        app_logger.workflow_stage_changed(
            thread_id=thread_id,
            stage="topics_generated",
            topics_count=len(generated_topics)
        )
        
        return StartWorkflowResponse(
            thread_id=thread_id,
            status=current_status,
            generated_topics=generated_topics,
            message="工作流已启动，请选择一个选题继续",
            interrupt_info=interrupt_info,
            node_metrics=node_metrics
        )
        
    except Exception as e:
        app_logger.workflow_error(
            thread_id=thread_id if 'thread_id' in dir() else "unknown",
            error=str(e),
            stage="start"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"启动工作流失败: {str(e)}"
        )


@router.get("/state/{thread_id}", response_model=WorkflowStateResponse)
async def get_workflow_state(
    thread_id: str,
    current_user: User = Depends(get_current_user)
) -> WorkflowStateResponse:
    """
    获取工作流当前状态
    
    Args:
        thread_id: 工作流线程ID
        
    Returns:
        当前工作流状态快照
    """
    try:
        # 验证 thread_id 属于当前用户
        if not thread_id.startswith(f"{current_user.id}_"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此工作流"
            )
        
        # 获取编译后的图
        graph = await get_graph()
        
        # 配置
        config = {"configurable": {"thread_id": thread_id}}
        
        # 获取状态快照
        state_snapshot = await graph.aget_state(config, subgraphs=True)
        
        if state_snapshot is None or not public_values(state_snapshot):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到工作流: {thread_id}"
            )
        
        # 获取下一个待执行节点
        next_nodes = list(state_snapshot.next) if state_snapshot.next else []
        
        # 判断是否已完成
        is_completed = len(next_nodes) == 0 and not extract_interrupt_info(state_snapshot) and public_values(state_snapshot).get("status") == "completed"
        
        # 获取中断信息
        interrupt_info = extract_interrupt_info(state_snapshot)
        
        # 获取节点指标
        node_metrics = public_values(state_snapshot).get("node_metrics", [])
        
        return WorkflowStateResponse(
            thread_id=thread_id,
            status=public_values(state_snapshot).get("status", "unknown"),
            values=dict(public_values(state_snapshot)),
            next_nodes=next_nodes,
            is_completed=is_completed,
            interrupt_info=interrupt_info,
            node_metrics=node_metrics
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取工作流状态失败: {str(e)}"
        )


@router.post("/resume/{thread_id}", response_model=ResumeWorkflowResponse)
async def resume_workflow(
    thread_id: str, 
    request: ResumeWorkflowRequest,
    current_user: User = Depends(get_current_user)
) -> ResumeWorkflowResponse:
    """
    恢复工作流运行 (LangGraph 1.0+ Command 模式)
    
    使用 Command 对象向中断的工作流提供用户输入并恢复执行
    
    Args:
        thread_id: 工作流线程ID
        request: 包含操作类型和数据的请求体
        
    Returns:
        恢复后的工作流状态
    """
    try:
        # 验证 thread_id 属于当前用户
        if not thread_id.startswith(f"{current_user.id}_"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此工作流"
            )
        
        # 获取编译后的图
        graph = await get_graph()
        
        # 配置
        config = {"configurable": {"thread_id": thread_id}}
        
        # 获取当前状态
        current_state = await graph.aget_state(config, subgraphs=True)
        
        if current_state is None or not current_state.values:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到工作流: {thread_id}"
            )
        
        validate_resume(current_state, request.action, request.data)

        # 根据操作类型构建 resume 数据
        # LangGraph 1.0+ 使用 Command(resume=value) 来恢复中断
        resume_value: Dict[str, Any] = {}
        
        if request.action == "select_topic":
            # 选择选题
            if not request.data or "selected_topic" not in request.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="选择选题需要提供 selected_topic"
                )
            resume_value = {
                "selected_topic": request.data["selected_topic"],
            }
            # 记录选题
            app_logger.topic_selected(
                thread_id=thread_id,
                selected_topic=request.data["selected_topic"]
            )
            
        elif request.action == "approve":
            # 审核通过
            resume_value = {
                "action": "approve",
            }
            # 记录审核通过
            app_logger.draft_approved(thread_id=thread_id)
            
        elif request.action == "reject":
            # 审核驳回
            feedback = request.data.get("feedback", "") if request.data else ""
            resume_value = {
                "action": "reject",
                "feedback": feedback,
            }
            # 记录驳回
            revision_count = current_state.values.get("revision_count", 0)
            app_logger.draft_rejected(
                thread_id=thread_id,
                feedback=feedback,
                revision_count=revision_count
            )
        
        # 使用 Command 恢复工作流
        # LangGraph 1.0+ 中，使用 ainvoke(Command(resume=value), config) 恢复
        resume_command = Command(resume=resume_value)
        
        # 恢复运行直到下一个中断点或结束
        result = await graph.ainvoke(resume_command, config)
        
        # 获取更新后的状态
        updated_state = await graph.aget_state(config, subgraphs=True)
        next_nodes = list(updated_state.next) if updated_state.next else []
        interrupt_info = extract_interrupt_info(updated_state)
        is_completed = len(next_nodes) == 0 and not interrupt_info and public_values(updated_state).get("status") == "completed"
        
        # 获取节点指标
        node_metrics = public_values(updated_state).get("node_metrics", [])
        
        # 构建响应
        message = "操作成功"
        final_result = None
        
        if is_completed or public_values(updated_state).get("status") == "images_failed":
            message = "工作流已完成"
            final_result = {
                "error": public_values(updated_state).get("error", ""),
                "article_content": public_values(updated_state).get("article_content", ""),
                "visual_points": public_values(updated_state).get("visual_points", []),
                "image_urls": public_values(updated_state).get("image_urls", []),
            }
            # 记录工作流完成
            app_logger.workflow_completed(thread_id=thread_id)
        elif interrupt_info:
            action_required = interrupt_info.get("action_required", "")
            if action_required == "review":
                message = "文章草稿已生成，请审核"
                # 记录草稿生成
                article_content = public_values(updated_state).get("article_content", "")
                app_logger.draft_generated(
                    thread_id=thread_id,
                    word_count=len(article_content)
                )
            elif action_required == "select_topic":
                message = "请选择选题"
            else:
                message = "等待用户操作"
        
        return ResumeWorkflowResponse(
            thread_id=thread_id,
            status=public_values(updated_state).get("status", "unknown"),
            message=message,
            next_nodes=next_nodes,
            is_completed=is_completed,
            result=final_result,
            interrupt_info=interrupt_info,
            node_metrics=node_metrics
        )
        
    except HTTPException:
        raise
    except Exception as e:
        app_logger.workflow_error(
            thread_id=thread_id,
            error=str(e),
            stage="resume"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"恢复工作流失败: {str(e)}"
        )


@router.get("/history/{thread_id}")
async def get_workflow_history(
    thread_id: str,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    获取工作流的历史状态记录
    
    Args:
        thread_id: 工作流线程ID
        
    Returns:
        历史状态列表
    """
    try:
        # 验证 thread_id 属于当前用户
        if not thread_id.startswith(f"{current_user.id}_"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此工作流"
            )
        
        # 获取编译后的图
        graph = await get_graph()
        
        # 配置
        config = {"configurable": {"thread_id": thread_id}}
        
        # 获取历史状态
        history = []
        async for state in graph.aget_state_history(config):
            history.append({
                "config": state.config,
                "values": dict(state.values) if state.values else {},
                "next": list(state.next) if state.next else [],
                "created_at": state.created_at if hasattr(state, "created_at") else None,
            })
        
        return {
            "thread_id": thread_id,
            "history": history[:20],  # 限制返回最近 20 条
            "total": len(history)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取工作流历史失败: {str(e)}"
        )


@router.get("/threads", response_model=ThreadListResponse)
async def get_all_threads(
    current_user: User = Depends(get_current_user)
) -> ThreadListResponse:
    """
    获取所有工作流线程列表
    
    Returns:
        线程列表，包含每个线程的基本信息
    """
    try:
        threads = []
        
        # 从 PostgreSQL 数据库查询
        async with await psycopg.AsyncConnection.connect(
            settings.postgres_uri,
            autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # 查询当前用户的 thread_id（根据用户ID前缀过滤）
                user_id_prefix = f"{current_user.id}\\_%"
                await cur.execute("""
                    SELECT DISTINCT thread_id 
                    FROM checkpoints 
                    WHERE thread_id LIKE %s
                    ORDER BY thread_id
                """, (user_id_prefix,))
                rows = await cur.fetchall()
                
                graph = await get_graph()
                
                for row in rows:
                    thread_id = row[0]
                    config = {"configurable": {"thread_id": thread_id}}
                    try:
                        state_snapshot = await graph.aget_state(config, subgraphs=True)
                        if state_snapshot and public_values(state_snapshot):
                            values = public_values(state_snapshot)
                            next_nodes = list(state_snapshot.next) if state_snapshot.next else []
                            interrupt_info = extract_interrupt_info(state_snapshot)
                            is_completed = len(next_nodes) == 0 and not interrupt_info and public_values(state_snapshot).get("status") == "completed"
                            
                            # 获取创建时间
                            created_at = None
                            if hasattr(state_snapshot, 'created_at') and state_snapshot.created_at:
                                created_at = state_snapshot.created_at
                            
                            threads.append(ThreadInfo(
                                thread_id=thread_id,
                                topic_direction=values.get("topic_direction", ""),
                                selected_topic=values.get("selected_topic", ""),
                                status=values.get("status", "unknown"),
                                is_completed=is_completed,
                                created_at=created_at
                            ))
                    except Exception:
                        continue
        
        return ThreadListResponse(
            threads=threads,
            total=len(threads)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取线程列表失败: {str(e)}"
        )


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    删除指定的工作流线程
    
    Args:
        thread_id: 工作流线程ID
        
    Returns:
        删除结果
    """
    try:
        # 验证 thread_id 属于当前用户
        if not thread_id.startswith(f"{current_user.id}_"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权删除此工作流"
            )
        
        # 从 PostgreSQL 数据库删除
        async with await psycopg.AsyncConnection.connect(
            settings.postgres_uri,
            autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # 删除相关记录
                await cur.execute(
                    "DELETE FROM checkpoint_writes WHERE thread_id = %s",
                    (thread_id,)
                )
                await cur.execute(
                    "DELETE FROM checkpoint_blobs WHERE thread_id = %s",
                    (thread_id,)
                )
                await cur.execute(
                    "DELETE FROM checkpoints WHERE thread_id = %s",
                    (thread_id,)
                )
                
                return {"success": True, "message": f"线程 {thread_id} 已删除"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除线程失败: {str(e)}"
        )


# ============== SSE 流式输出请求模型 ==============
# 注意：流式输出仅用于文章生成场景（select_topic 和 reject 操作）
# 选题阶段和审核通过阶段不需要流式，请使用普通接口

class StreamResumeWorkflowRequest(BaseModel):
    """
    流式恢复工作流请求
    
    仅支持需要文章生成的操作：
    - select_topic: 选择选题后生成文章（需要流式）
    - reject: 驳回后重新生成文章（需要流式）
    
    审核通过(approve)请使用普通接口 POST /resume/{thread_id}
    """
    action: Literal["select_topic", "reject"] = Field(
        ..., 
        description="操作类型：select_topic(选择选题后生成文章)、reject(驳回后重新生成文章)"
    )
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="操作数据，select_topic时需要selected_topic，reject时可提供feedback"
    )


# ============== SSE 流式输出 API (使用官方 graph.astream) ==============

def format_sse_event(event_type: str, data: Any) -> str:
    """
    将事件格式化为SSE格式
    
    Args:
        event_type: 事件类型
        data: 事件数据
        
    Returns:
        SSE格式字符串
    """
    payload = {
        "type": event_type,
        "data": data
    }
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


async def stream_graph_updates(
    graph, 
    input_data: Any, 
    config: Dict[str, Any]
) -> AsyncGenerator[str, None]:
    """
    使用 LangGraph astream_events 流式输出文章生成过程
    
    专门用于文章生成场景，提供 token 级别的流式输出
    
    Args:
        graph: 编译后的图
        input_data: 输入数据 (Command 对象)
        config: 配置 (包含 thread_id)
        
    Yields:
        SSE格式的事件字符串
    """
    try:
        # 发送开始事件
        yield format_sse_event("start", {})
        
        # 用于收集 token 统计
        token_stats = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }
        
        # 使用 astream_events 获取 LLM token 级别的流式输出
        async for event in graph.astream_events(input_data, config, version="v2"):
            event_kind = event.get("event", "")
            event_name = event.get("name", "")
            event_data = event.get("data", {})
            
            if event_kind == "on_chat_model_start":
                yield format_sse_event("llm_start", {
                    "model": event_name
                })
                
            elif event_kind == "on_chat_model_stream":
                # LLM token 级别的流式输出 - 文章生成的核心
                chunk = event_data.get("chunk", {})
                if hasattr(chunk, "content") and chunk.content:
                    yield format_sse_event("llm_token", {
                        "content": chunk.content
                    })
                    
            elif event_kind == "on_chat_model_end":
                output = event_data.get("output", {})
                # 提取 token 使用信息
                usage_info = {}
                if hasattr(output, "usage_metadata") and output.usage_metadata:
                    usage_info = {
                        "input_tokens": output.usage_metadata.get("input_tokens", 0),
                        "output_tokens": output.usage_metadata.get("output_tokens", 0),
                        "total_tokens": output.usage_metadata.get("total_tokens", 0)
                    }
                    token_stats.update(usage_info)
                elif hasattr(output, "response_metadata") and output.response_metadata:
                    token_usage = output.response_metadata.get("token_usage", {})
                    if token_usage:
                        usage_info = {
                            "input_tokens": token_usage.get("prompt_tokens", 0),
                            "output_tokens": token_usage.get("completion_tokens", 0),
                            "total_tokens": token_usage.get("total_tokens", 0)
                        }
                        token_stats.update(usage_info)
                
                yield format_sse_event("llm_end", {
                    "model": event_name,
                    "usage": usage_info if usage_info else token_stats
                })
        
        # 获取最终状态
        final_state = await graph.aget_state(config, subgraphs=True)
        interrupt_info = extract_interrupt_info(final_state)
        next_nodes = list(final_state.next) if final_state.next else []
        is_completed = len(next_nodes) == 0 and not interrupt_info and public_values(final_state).get("status") == "completed"
        
        # 发送完成事件
        yield format_sse_event("done", {
            "status": public_values(final_state).get("status", "unknown") if public_values(final_state) else "unknown",
            "next_nodes": next_nodes,
            "is_completed": is_completed,
            "interrupt_info": interrupt_info,
            "values": dict(public_values(final_state)) if public_values(final_state) else {}
        })
        
    except Exception as e:
        # 发送错误事件
        yield format_sse_event("error", {"message": str(e)})


@router.post("/stream/resume/{thread_id}")
async def stream_resume_workflow(
    thread_id: str, 
    request: StreamResumeWorkflowRequest,
    current_user: User = Depends(get_current_user)
):
    """
    流式恢复工作流 - 仅用于文章生成场景
    
    使用 Server-Sent Events (SSE) 实时返回 LLM 生成的文章内容（token 级别流式输出）
    
    支持的操作：
    - select_topic: 选择选题后，流式生成文章
    - reject: 驳回审核后，流式重新生成文章
    
    注意：审核通过(approve)不需要流式，请使用普通接口 POST /resume/{thread_id}
    
    事件类型说明：
    - resume: 恢复开始
    - llm_start: LLM 开始生成
    - llm_token: LLM 输出的每个 token（文章内容逐字输出）
    - llm_end: LLM 生成完成，包含 token 统计
    - done: 工作流阶段完成
    - error: 错误信息
    """
    # 验证 thread_id 属于当前用户
    if not thread_id.startswith(f"{current_user.id}_"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此工作流"
        )
    
    graph = await get_graph()
    current = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    validate_resume(current, request.action, request.data)

    async def generate():
        try:
            # 获取编译后的图
            graph = await get_graph()
            
            # 配置
            config = {"configurable": {"thread_id": thread_id}}
            
            # 获取当前状态
            current_state = await graph.aget_state(config, subgraphs=True)
            
            if current_state is None or not current_state.values:
                yield format_sse_event("error", {"message": f"未找到工作流: {thread_id}"})
                return
            
            # 根据操作类型构建 resume 数据
            resume_value: Dict[str, Any] = {}
            
            if request.action == "select_topic":
                if not request.data or "selected_topic" not in request.data:
                    yield format_sse_event("error", {"message": "选择选题需要提供 selected_topic"})
                    return
                resume_value = {
                    "selected_topic": request.data["selected_topic"],
                }
                
            elif request.action == "reject":
                feedback = request.data.get("feedback", "") if request.data else ""
                resume_value = {
                    "action": "reject",
                    "feedback": feedback,
                }
            
            # 使用 Command 恢复工作流
            resume_command = Command(resume=resume_value)
            
            # 发送恢复信息
            yield format_sse_event("resume", {
                "thread_id": thread_id,
                "action": request.action
            })
            
            # 流式输出文章生成过程
            async for event in stream_graph_updates(graph, resume_command, config):
                yield event
                
        except Exception as e:
            yield format_sse_event("error", {"message": str(e)})
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/retry/{thread_id}", response_model=WorkflowStateResponse)
async def retry_workflow(thread_id: str, current_user: User = Depends(get_current_user)):
    """Retry a failed node, or regenerate the picture batch after a partial failure."""
    if not thread_id.startswith(f"{current_user.id}_"):
        raise HTTPException(403, "无权访问此工作流")
    graph = await get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = await graph.aget_state(config, subgraphs=True)
    if not snapshot or not snapshot.values:
        raise HTTPException(404, "未找到工作流")
    if snapshot.values.get("status") == "images_failed":
        await graph.aupdate_state(config, {"error": "", "image_urls": []}, as_node="extract_visuals")
    elif extract_interrupt_info(snapshot) or not snapshot.next:
        raise HTTPException(409, "此工作流没有可重试的失败节点")
    try:
        await graph.ainvoke(None, config)
    except Exception as exc:
        raise HTTPException(502, "节点重试失败，请检查模型服务配置及配额") from exc
    return await get_workflow_state(thread_id, current_user)
