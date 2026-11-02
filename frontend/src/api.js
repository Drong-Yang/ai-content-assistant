import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 120000 // 2分钟超时，因为 AI 生成需要时间
})

// ============== 认证相关 ==============

// 获取 token
export function getToken() {
  return localStorage.getItem('token')
}

// 设置 token
export function setToken(token) {
  localStorage.setItem('token', token)
}

// 移除 token
export function removeToken() {
  localStorage.removeItem('token')
}

// 检查是否已登录
export function isLoggedIn() {
  return !!getToken()
}

// 请求拦截器 - 自动添加 token
api.interceptors.request.use(
  config => {
    const token = getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  error => Promise.reject(error)
)

// 响应拦截器 - 401 时触发登出
api.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      removeToken()
      // 触发自定义事件通知前端需要登录
      window.dispatchEvent(new CustomEvent('auth:logout'))
    }
    return Promise.reject(error)
  }
)

// 用户注册
export async function register(username, password) {
  const res = await api.post('/auth/register', { username, password })
  return res.data
}

// 用户登录
export async function login(username, password) {
  const res = await api.post('/auth/login', { username, password })
  if (res.data.access_token) {
    setToken(res.data.access_token)
  }
  return res.data
}

// 获取当前用户信息
export async function getCurrentUser() {
  const res = await api.get('/auth/me')
  return res.data
}

// 登出
export function logout() {
  removeToken()
}

// 启动工作流
export async function startWorkflow(topicDirection) {
  const res = await api.post('/workflow/start', {
    topic_direction: topicDirection
  })
  return res.data
}

// 获取工作流状态
export async function getWorkflowState(threadId) {
  const res = await api.get(`/workflow/state/${threadId}`)
  return res.data
}

// 恢复工作流 - 选择选题
export async function selectTopic(threadId, selectedTopic) {
  const res = await api.post(`/workflow/resume/${threadId}`, {
    action: 'select_topic',
    data: { selected_topic: selectedTopic }
  })
  return res.data
}

// 恢复工作流 - 审核通过
export async function approveArticle(threadId) {
  const res = await api.post(`/workflow/resume/${threadId}`, {
    action: 'approve'
  })
  return res.data
}

// 恢复工作流 - 审核驳回
export async function rejectArticle(threadId, feedback) {
  const res = await api.post(`/workflow/resume/${threadId}`, {
    action: 'reject',
    data: { feedback }
  })
  return res.data
}

// 获取工作流历史
export async function getWorkflowHistory(threadId) {
  const res = await api.get(`/workflow/history/${threadId}`)
  return res.data
}

// 获取所有工作流线程列表
export async function getAllThreads() {
  const res = await api.get('/workflow/threads')
  return res.data
}

// 删除工作流线程
export async function deleteThread(threadId) {
  const res = await api.delete(`/workflow/threads/${threadId}`)
  return res.data
}

// ============== 流式 API（仅用于文章生成场景） ==============
// 选题阶段和审核通过请使用普通接口 startWorkflow / approveArticle

/**
 * 流式启动工作流 - 选题阶段使用非流式结构化输出，包装成回调形式
 * @param {string} topicDirection - 主题方向
 * @param {Object} callbacks - 回调函数对象
 * @param {string} streamMode - 流模式（此场景下忽略，使用普通 API）
 */
export async function streamStartWorkflow(topicDirection, callbacks, streamMode = 'updates', options = {}) {
  try {
    // 先生成一个临时 thread_id 用于初始化回调
    callbacks.onInit?.({ thread_id: 'loading...' })
    callbacks.onStart?.({ stream_mode: streamMode })
    
    // 调用普通 API
    const res = await api.post('/workflow/start', {
      topic_direction: topicDirection,
      ...options
    })
    const data = res.data
    
    // 模拟流式事件回调
    callbacks.onInit?.({ thread_id: data.thread_id })
    
    // 节点结束事件
    callbacks.onNodeEnd?.({
      node: 'plan_topics',
      metrics: data.node_metrics?.[0] || null
    })
    
    // 更新事件
    callbacks.onUpdate?.('topic_selection', {
      generated_topics: data.generated_topics,
      node_metrics: data.node_metrics
    })
    
    // 完成事件
    callbacks.onDone?.({
      status: data.status,
      interrupt_info: data.interrupt_info,
      values: {
        generated_topics: data.generated_topics,
        node_metrics: data.node_metrics
      }
    })
    
  } catch (error) {
    callbacks.onError?.(error.response?.data?.detail || error.message)
  }
}

/**
 * 流式审核通过 - 使用非流式 API，包装成回调形式
 * @param {string} threadId - 线程ID
 * @param {Object} callbacks - 回调函数对象
 * @param {string} streamMode - 流模式（此场景下忽略，使用普通 API）
 */
export async function streamApproveArticle(threadId, callbacks, streamMode = 'updates') {
  try {
    callbacks.onResume?.({ thread_id: threadId, action: 'approve' })
    callbacks.onStart?.({ stream_mode: streamMode })
    
    // 调用普通 API
    const res = await api.post(`/workflow/resume/${threadId}`, {
      action: 'approve'
    })
    const data = res.data
    
    // 更新事件 - 视觉要点
    if (data.result?.visual_points) {
      callbacks.onUpdate?.('extract_visuals', {
        visual_points: data.result.visual_points,
        node_metrics: data.node_metrics
      })
    }
    
    // 更新事件 - 图片
    if (data.result?.image_urls) {
      callbacks.onUpdate?.('generate_images', {
        image_urls: data.result.image_urls,
        node_metrics: data.node_metrics
      })
    }
    
    // 完成事件
    callbacks.onDone?.({
      status: data.status,
      is_completed: data.is_completed,
      interrupt_info: data.interrupt_info,
      values: {
        ...data.values,
        error: data.result?.error || '',
        article_content: data.result?.article_content || '',
        visual_points: data.result?.visual_points || [],
        image_urls: data.result?.image_urls || [],
        node_metrics: data.node_metrics
      }
    })
    
  } catch (error) {
    callbacks.onError?.(error.response?.data?.detail || error.message)
  }
}

/**
 * SSE 事件处理器 - 用于文章生成的流式输出
 * @param {Response} response - fetch 响应对象
 * @param {Object} callbacks - 回调函数对象
 * @param {Function} callbacks.onStart - 开始事件
 * @param {Function} callbacks.onLlmStart - LLM 开始生成
 * @param {Function} callbacks.onLlmToken - LLM token 事件 (content) - 文章逐字输出
 * @param {Function} callbacks.onLlmEnd - LLM 生成完成，包含 token 统计
 * @param {Function} callbacks.onDone - 完成事件 (finalState)
 * @param {Function} callbacks.onError - 错误事件 (message)
 */
async function handleSSEStream(response, callbacks) {
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }
  
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let receivedFinal = false
  
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const event = JSON.parse(line.slice(6))
          const { type, data } = event
          
          switch (type) {
            case 'node_start':
              callbacks.onNodeStart?.(data)
              break
            case 'node_end':
              callbacks.onNodeEnd?.(data)
              callbacks.onUpdate?.(data.node, data.output || {})
              break
            case 'start':
              callbacks.onStart?.(data)
              break
            case 'resume':
              callbacks.onResume?.(data)
              break
            case 'llm_start':
              callbacks.onLlmStart?.(data)
              break
            case 'llm_token':
              callbacks.onLlmToken?.(data.content)
              break
            case 'llm_end':
              callbacks.onLlmEnd?.(data)
              break
            case 'done':
              receivedFinal = true
              callbacks.onDone?.(data)
              break
            case 'error':
              receivedFinal = true
              callbacks.onError?.(data.message)
              break
          }
        } catch (e) {
          console.error('解析SSE数据失败:', e, line)
        }
      }
    }
  }
  if (!receivedFinal) throw new Error('生成连接中断，请刷新状态后重试')
}

/**
 * 流式选择选题 - 选题后流式生成文章
 * @param {string} threadId - 线程ID
 * @param {string} selectedTopic - 选中的选题
 * @param {Object} callbacks - 回调函数对象
 */
export function streamSelectTopic(threadId, selectedTopic, callbacks) {
  const token = getToken()
  return fetch(`/api/v1/workflow/stream/resume/${threadId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    },
    body: JSON.stringify({
      action: 'select_topic',
      data: { selected_topic: selectedTopic }
    })
  }).then(response => handleSSEStream(response, callbacks))
}

/**
 * 流式驳回重写 - 驳回后流式重新生成文章
 * @param {string} threadId - 线程ID
 * @param {string} feedback - 修改意见
 * @param {Object} callbacks - 回调函数对象
 */
export function streamRejectArticle(threadId, feedback, callbacks) {
  const token = getToken()
  return fetch(`/api/v1/workflow/stream/resume/${threadId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    },
    body: JSON.stringify({
      action: 'reject',
      data: { feedback: feedback || '' }
    })
  }).then(response => handleSSEStream(response, callbacks))
}

export async function retryWorkflow(threadId) {
  return (await api.post(`/workflow/retry/${threadId}`)).data
}
