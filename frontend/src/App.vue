<template>
  <!-- 登录/注册页面 -->
  <div v-if="!isLoggedIn" class="auth-page">
    <div class="auth-container">
      <div class="auth-card">
        <h2>{{ isLoginMode ? '登录' : '注册' }}</h2>
        <form @submit.prevent="handleAuth">
          <div class="form-group">
            <label>用户名</label>
            <input 
              v-model="authForm.username" 
              type="text" 
              class="input"
              placeholder="请输入用户名（至少3个字符）"
              required 
              minlength="3"
            />
          </div>
          <div class="form-group">
            <label>密码</label>
            <input 
              v-model="authForm.password" 
              type="password" 
              class="input"
              placeholder="请输入密码（至少6个字符）"
              required 
              minlength="6"
            />
          </div>
          <div v-if="authError" class="auth-error">
            {{ authError }}
          </div>
          <button 
            type="submit" 
            class="btn btn-primary auth-btn"
            :disabled="authLoading"
          >
            {{ authLoading ? '处理中...' : (isLoginMode ? '登录' : '注册') }}
          </button>
        </form>
        <div class="auth-switch">
          <span v-if="isLoginMode">
            还没有账号？
            <a href="#" @click.prevent="isLoginMode = false">立即注册</a>
          </span>
          <span v-else>
            已有账号？
            <a href="#" @click.prevent="isLoginMode = true">立即登录</a>
          </span>
        </div>
      </div>
    </div>
  </div>

  <!-- 主应用页面 -->
  <div v-else class="app-layout">
    <!-- 历史记录侧边栏 -->
    <div class="sidebar" :class="{ collapsed: !sidebarOpen }">
      <div class="sidebar-header">
        <h3 v-if="sidebarOpen">历史记录</h3>
        <button class="sidebar-toggle" @click="sidebarOpen = !sidebarOpen">
          {{ sidebarOpen ? '◀' : '▶' }}
        </button>
      </div>
      
      <div v-if="sidebarOpen" class="sidebar-content">
        <button class="btn btn-primary sidebar-btn" @click="handleNewWorkflow">
          + 新建工作流
        </button>
        
        <div class="thread-list">
          <div v-if="loadingThreads" class="loading-small">
            <div class="loading-spinner-small"></div>
          </div>
          
          <div v-else-if="threadList.length === 0" class="empty-state">
            暂无历史记录
          </div>
          
          <div 
            v-else
            v-for="thread in threadList" 
            :key="thread.thread_id"
            class="thread-item"
            :class="{ active: threadId === thread.thread_id }"
            @click="handleSwitchThread(thread.thread_id)"
          >
            <div class="thread-item-header">
              <span class="thread-status" :class="thread.is_completed ? 'completed' : 'in-progress'">
                {{ thread.is_completed ? '✓' : '●' }}
              </span>
              <span class="thread-title">{{ thread.topic_direction || '未命名' }}</span>
            </div>
            <div class="thread-item-meta">
              <span class="thread-topic">{{ thread.selected_topic || thread.status }}</span>
            </div>
            <button 
              class="thread-delete-btn" 
              @click.stop="handleDeleteThread(thread.thread_id)"
              title="删除"
            >
              ×
            </button>
          </div>
        </div>
        
        <button 
          v-if="threadList.length > 0"
          class="btn sidebar-btn refresh-btn" 
          @click="fetchThreadList"
          :disabled="loadingThreads"
        >
          刷新列表
        </button>
      </div>
    </div>

    <!-- 主内容区域 -->
    <div class="main-content">
      <div class="container">
        <!-- 头部 -->
        <div class="header">
          <div class="header-top">
            <div>
              <h1>AI 内容运营助手</h1>
              <p>基于 LangGraph 的智能内容生成工作流</p>
            </div>
            <div class="user-info">
              <span class="username">{{ currentUsername }}</span>
              <button class="btn btn-logout" @click="handleLogout">退出登录</button>
            </div>
          </div>
        </div>

    <!-- 工作流进度条 -->
    <div class="card">
      <div class="workflow-steps">
        <div class="step" :class="{ active: currentStep === 0, completed: currentStep > 0 }">
          <div class="step-icon">1</div>
          <div class="step-title">输入主题</div>
        </div>
        <div class="step" :class="{ active: currentStep === 1, completed: currentStep > 1 }">
          <div class="step-icon">2</div>
          <div class="step-title">选择选题</div>
        </div>
        <div class="step" :class="{ active: currentStep === 2, completed: currentStep > 2 }">
          <div class="step-icon">3</div>
          <div class="step-title">审核文章</div>
        </div>
        <div class="step" :class="{ active: currentStep === 3, completed: currentStep > 3 }">
          <div class="step-icon">4</div>
          <div class="step-title">生成配图</div>
        </div>
        <div class="step" :class="{ active: currentStep === 4, completed: currentStep > 4 }">
          <div class="step-icon">✓</div>
          <div class="step-title">完成</div>
        </div>
      </div>
    </div>

    <!-- 消息提示 -->
    <div v-if="message" :class="['message', `message-${messageType}`]">
      {{ message }}
    </div>

    <!-- 当前工作流信息（步骤0以外时显示主题方向） -->
    <div v-if="currentStep > 0 && topicDirection" class="current-workflow-info">
      <div class="workflow-info-item">
        <span class="workflow-info-label">主题方向：</span>
        <span class="workflow-info-value">{{ topicDirection }}</span>
      </div>
      <div v-if="selectedTopic" class="workflow-info-item">
        <span class="workflow-info-label">已选选题：</span>
        <span class="workflow-info-value">{{ selectedTopic }}</span>
      </div>
    </div>

    <!-- 步骤 0: 输入主题 -->
    <div v-if="currentStep === 0" class="card">
      <div class="card-title">输入主题方向</div>
      <div style="display: flex; gap: 12px;">
        <input 
          v-model="topicDirection" 
          class="input" 
          placeholder="请输入内容主题方向，例如：AI技术、Python开发、职场技能"
          @keyup.enter="handleStart"
        />
        <button 
          class="btn btn-primary" 
          :disabled="!topicDirection.trim() || loading"
          @click="handleStart"
        >
          {{ loading ? '生成中...' : '开始' }}
        </button>
      </div>
    </div>

    <!-- 步骤 1: 选择选题 -->
    <div v-if="currentStep === 1" class="card">
      <div class="card-title">请选择一个选题</div>
      <!-- 流式生成中：显示实时内容 -->
      <div v-if="loading && streamingTopicsText" class="streaming-content">
        <div class="streaming-label">AI 正在生成选题...</div>
        <div class="streaming-text">
          {{ streamingTopicsText }}
          <span class="typing-cursor">▊</span>
        </div>
      </div>
      <!-- 加载中但还没有内容 -->
      <div v-else-if="loading && generatedTopics.length === 0 && !streamingTopicsText" class="loading">
        <div class="loading-spinner"></div>
        <p style="margin-top: 12px;">AI 正在生成选题...</p>
      </div>
      <!-- 已生成选题列表 -->
      <div v-else class="topic-list">
        <div 
          v-for="(topic, index) in generatedTopics" 
          :key="index"
          class="topic-item"
          :class="{ selected: selectedTopic === topic }"
          @click="selectedTopic = topic"
        >
          {{ topic }}
        </div>
        <div v-if="loading && generatedTopics.length > 0" class="loading-small" style="margin-top: 12px;">
          <div class="loading-spinner-small"></div>
          <span style="margin-left: 8px; color: #666;">正在生成更多选题...</span>
        </div>
      </div>
      <div class="btn-group">
        <button 
          class="btn btn-primary" 
          :disabled="!selectedTopic || loading"
          @click="handleSelectTopic"
        >
          确认选题
        </button>
        <button class="btn" style="background: #f0f0f0;" @click="handleReset">
          重新开始
        </button>
      </div>
    </div>

    <!-- 步骤 2: 审核文章 -->
    <div v-if="currentStep === 2" class="card">
      <div class="card-title">审核文章草稿</div>
      <div v-if="loading && !articleContent" class="loading">
        <div class="loading-spinner"></div>
        <p style="margin-top: 12px;">AI 正在撰写文章...</p>
      </div>
      <template v-else>
        <div class="article-content">
          {{ articleContent }}
          <span v-if="loading" class="typing-cursor">▊</span>
        </div>
        <div class="feedback-section">
          <label>驳回反馈（可选）:</label>
          <textarea 
            v-model="feedback" 
            class="textarea" 
            placeholder="如果需要驳回，请输入修改意见..."
            :disabled="loading"
          ></textarea>
        </div>
        <div class="btn-group">
          <button 
            class="btn btn-success" 
            :disabled="loading"
            @click="handleApprove"
          >
            通过
          </button>
          <button 
            class="btn btn-danger" 
            :disabled="loading"
            @click="handleReject"
          >
            驳回重写
          </button>
        </div>
      </template>
    </div>

    <!-- 步骤 3: 生成配图中 -->
    <div v-if="currentStep === 3" class="card">
      <div class="card-title">正在生成配图</div>
      
      <!-- 显示配图摘要（视觉要点） -->
      <div v-if="visualPoints.length > 0" class="visual-summary">
        <div class="visual-summary-title">配图摘要（AI 提取的视觉要点）</div>
        <ul class="visual-summary-list">
          <li v-for="(point, index) in visualPoints" :key="index">
            <span class="visual-point-index">{{ index + 1 }}</span>
            <span class="visual-point-text">{{ point }}</span>
          </li>
        </ul>
      </div>
      
      <div class="loading">
        <div class="loading-spinner"></div>
        <p style="margin-top: 12px;">AI 正在根据配图摘要生成图片...</p>
      </div>
    </div>

    <div v-if="workflowError || (threadId && !loading && !interruptInfo && workflowStatus !== 'completed')" class="card" role="alert">
      <p>{{ workflowError || '生成未完成，可尝试重新生成。' }}</p>
      <button class="btn btn-primary" :disabled="loading" @click="handleRetry">重试生成</button>
    </div>

    <!-- 步骤 4: 完成 -->
    <div v-if="currentStep === 4">
      <div class="card">
        <div class="card-title">最终文章</div>
        <div class="article-content">{{ articleContent }}</div>
      </div>
      
      <div v-if="imageUrls.length > 0" class="card">
        <div class="card-title">生成的配图</div>
        <div class="image-grid">
          <div v-for="(url, index) in imageUrls" :key="index" class="image-item">
            <img :src="url" :alt="'配图 ' + (index + 1)" />
          </div>
        </div>
      </div>

      <div v-if="visualPoints.length > 0" class="card">
        <div class="card-title">视觉要点</div>
        <ul style="padding-left: 20px;">
          <li v-for="(point, index) in visualPoints" :key="index" style="margin-bottom: 8px;">
            {{ point }}
          </li>
        </ul>
      </div>

      <div class="btn-group">
        <button class="btn btn-primary" @click="handleReset">
          开始新的创作
        </button>
      </div>
    </div>

    <!-- 节点执行指标面板 - 有数据就显示 -->
    <div v-if="nodeMetrics.length > 0" class="card">
      <div class="metrics-panel">
        <div class="metrics-panel-title">节点执行指标</div>
        
        <!-- 汇总统计 -->
        <div class="metrics-summary">
          <div class="metrics-summary-item">
            <div class="metrics-summary-value">{{ totalDuration }}</div>
            <div class="metrics-summary-label">总耗时</div>
          </div>
          <div class="metrics-summary-item">
            <div class="metrics-summary-value">{{ totalTokens.toLocaleString() }}</div>
            <div class="metrics-summary-label">总Token</div>
          </div>
          <div class="metrics-summary-item">
            <div class="metrics-summary-value">{{ nodeMetrics.length }}</div>
            <div class="metrics-summary-label">已执行节点</div>
          </div>
        </div>
        
        <!-- 各节点详情 -->
        <div class="metrics-list">
          <div v-for="(metric, index) in nodeMetrics" :key="index" class="metrics-item">
            <div class="metrics-node-name">{{ getNodeDisplayName(metric.node_name) }}</div>
            <div class="metrics-node-details">
              <div class="metrics-detail">
                <span class="metrics-detail-label">耗时:</span>
                <span class="metrics-detail-value highlight">{{ formatDuration(metric.duration_ms) }}</span>
              </div>
              <div class="metrics-detail">
                <span class="metrics-detail-label">输入:</span>
                <span class="metrics-detail-value">{{ metric.input_tokens || 0 }} tokens</span>
              </div>
              <div class="metrics-detail">
                <span class="metrics-detail-label">输出:</span>
                <span class="metrics-detail-value">{{ metric.output_tokens || 0 }} tokens</span>
              </div>
              <div class="metrics-detail">
                <span class="metrics-detail-label">总计:</span>
                <span class="metrics-detail-value highlight">{{ metric.total_tokens || 0 }} tokens</span>
              </div>
              <div v-if="metric.model" class="metrics-detail">
                <span class="metrics-detail-label">模型:</span>
                <span class="metrics-detail-value">{{ metric.model }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 调试信息 -->
    <div v-if="threadId" class="card" style="margin-top: 20px; background: #fafafa;">
      <div class="card-title" style="font-size: 14px; color: #666;">工作流信息</div>
      <div style="font-size: 12px; color: #999;">
        <p>Thread ID: {{ threadId }}</p>
        <p>当前状态: {{ workflowStatus }}</p>
        <p v-if="interruptInfo">中断信息: {{ JSON.stringify(interruptInfo) }}</p>
      </div>
    </div>

    <!-- 流式日志面板 -->
    <div class="card stream-log-card">
      <div class="stream-log-header" @click="streamLogOpen = !streamLogOpen">
        <div class="stream-log-title">
          <span class="stream-log-icon">📡</span>
          Graph 流式输出日志
          <span class="stream-log-badge" v-if="streamLogs.length > 0">{{ streamLogs.length }}</span>
        </div>
        <div class="stream-log-actions">
          <button 
            class="stream-log-clear-btn" 
            @click.stop="clearStreamLogs"
            v-if="streamLogs.length > 0"
          >
            清空
          </button>
          <span class="stream-log-toggle">{{ streamLogOpen ? '▼' : '▶' }}</span>
        </div>
      </div>
      
      <div v-if="streamLogOpen" class="stream-log-content">
        <div v-if="streamLogs.length === 0" class="stream-log-empty">
          暂无日志，启动工作流后将显示流式输出数据
        </div>
        <div v-else class="stream-log-list" ref="streamLogList">
          <div 
            v-for="(log, index) in streamLogs" 
            :key="index" 
            class="stream-log-item"
            :class="['log-type-' + log.type]"
          >
            <div class="log-header">
              <span class="log-time">{{ log.time }}</span>
              <span class="log-type-badge" :class="'badge-' + log.type">{{ log.type }}</span>
              <span class="log-source" v-if="log.source">{{ log.source }}</span>
            </div>
            <div class="log-content">
              <template v-if="log.type === 'llm_token'">
                <span class="log-token">{{ log.content }}</span>
              </template>
              <template v-else-if="log.data">
                <pre class="log-data">{{ formatLogData(log.data) }}</pre>
              </template>
              <template v-else>
                <span>{{ log.message }}</span>
              </template>
            </div>
          </div>
        </div>
        
        <!-- 日志统计 -->
        <div class="stream-log-stats" v-if="streamLogs.length > 0">
          <div class="stat-item">
            <span class="stat-label">总事件:</span>
            <span class="stat-value">{{ streamLogs.length }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">Token数:</span>
            <span class="stat-value">{{ tokenCount }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">节点更新:</span>
            <span class="stat-value">{{ updateCount }}</span>
          </div>
        </div>
      </div>
    </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { 
  retryWorkflow,
  startWorkflow, 
  getWorkflowState, 
  selectTopic as apiSelectTopic,
  approveArticle,
  rejectArticle,
  getAllThreads,
  deleteThread,
  // 新的流式 API (使用 LangGraph 官方 graph.astream)
  streamStartWorkflow,
  streamSelectTopic,
  streamApproveArticle,
  streamRejectArticle,
  // 认证相关
  login,
  register,
  logout,
  isLoggedIn as checkLoggedIn,
  getCurrentUser
} from './api.js'

// ============== 认证状态 ==============
const isLoggedIn = ref(false)
const isLoginMode = ref(true)
const authLoading = ref(false)
const authError = ref('')
const currentUsername = ref('')
const authForm = ref({
  username: '',
  password: ''
})

// 检查登录状态
async function checkAuth() {
  if (checkLoggedIn()) {
    try {
      const user = await getCurrentUser()
      currentUsername.value = user.username
      isLoggedIn.value = true
    } catch (e) {
      isLoggedIn.value = false
    }
  }
}

// 处理登录/注册
async function handleAuth() {
  authError.value = ''
  authLoading.value = true
  
  try {
    if (isLoginMode.value) {
      // 登录
      await login(authForm.value.username, authForm.value.password)
      const user = await getCurrentUser()
      currentUsername.value = user.username
      isLoggedIn.value = true
      // 清空表单
      authForm.value = { username: '', password: '' }
    } else {
      // 注册
      await register(authForm.value.username, authForm.value.password)
      // 注册成功后自动登录
      await login(authForm.value.username, authForm.value.password)
      const user = await getCurrentUser()
      currentUsername.value = user.username
      isLoggedIn.value = true
      // 清空表单
      authForm.value = { username: '', password: '' }
    }
  } catch (e) {
    authError.value = e.response?.data?.detail || e.message || '操作失败'
  } finally {
    authLoading.value = false
  }
}

// 登出
function handleLogout() {
  logout()
  isLoggedIn.value = false
  currentUsername.value = ''
  // 重置工作流状态
  handleReset()
  threadList.value = []
}

// 监听 401 事件
function onAuthLogout() {
  isLoggedIn.value = false
  currentUsername.value = ''
}

onMounted(() => {
  checkAuth()
  window.addEventListener('auth:logout', onAuthLogout)
})

onUnmounted(() => {
  window.removeEventListener('auth:logout', onAuthLogout)
})

// 登录后获取历史记录
watch(isLoggedIn, (newVal) => {
  if (newVal) {
    fetchThreadList()
  }
})

// 侧边栏状态
const sidebarOpen = ref(true)
const loadingThreads = ref(false)
const threadList = ref([])

// 流式日志状态
const streamLogOpen = ref(true)
const streamLogs = ref([])
const streamLogList = ref(null)

// 日志统计
const tokenCount = computed(() => {
  return streamLogs.value.filter(log => log.type === 'llm_token').length
})

const updateCount = computed(() => {
  return streamLogs.value.filter(log => log.type === 'update').length
})

// 添加日志
function addStreamLog(type, data, source = '') {
  const now = new Date()
  const time = now.toLocaleTimeString('zh-CN', { 
    hour12: false, 
    hour: '2-digit', 
    minute: '2-digit', 
    second: '2-digit',
    fractionalSecondDigits: 3
  })
  
  const log = {
    type,
    time,
    source,
    ...(type === 'llm_token' ? { content: data } : { data, message: getLogMessage(type, data) })
  }
  
  streamLogs.value.push(log)
  
  // 限制日志数量，避免内存溢出
  if (streamLogs.value.length > 500) {
    streamLogs.value = streamLogs.value.slice(-400)
  }
  
  // 自动滚动到底部
  nextTick(() => {
    if (streamLogList.value) {
      streamLogList.value.scrollTop = streamLogList.value.scrollHeight
    }
  })
}

// 获取日志描述消息
function getLogMessage(type, data) {
  const messages = {
    'init': `工作流初始化 - Thread ID: ${data?.thread_id || ''}`,
    'start': `开始执行 - 模式: ${data?.stream_mode || ''}`,
    'resume': `恢复工作流 - 操作: ${data?.action || ''}`,
    'update': `节点更新 - ${data?.node || ''}`,
    'state': '状态快照更新',
    'node_start': `节点开始 - ${data?.node || ''}`,
    'node_end': `节点结束 - ${data?.node || ''}`,
    'llm_start': `LLM 开始调用 - ${data?.model || ''}`,
    'llm_end': `LLM 调用结束`,
    'done': `执行完成 - 状态: ${data?.status || ''}`,
    'error': `错误: ${data?.message || data || ''}`
  }
  return messages[type] || type
}

// 格式化日志数据
function formatLogData(data) {
  if (!data) return ''
  try {
    // 对于大数据进行截断
    const str = JSON.stringify(data, null, 2)
    if (str.length > 1000) {
      return str.substring(0, 1000) + '\n... (数据已截断)'
    }
    return str
  } catch (e) {
    return String(data)
  }
}

// 清空日志
function clearStreamLogs() {
  streamLogs.value = []
}

// 状态
const currentStep = ref(0)
const loading = ref(false)
const workflowError = ref("")
const message = ref('')
const messageType = ref('info')

// 工作流数据
const threadId = ref('')
const workflowStatus = ref('')
const interruptInfo = ref(null)

// 步骤数据
const topicDirection = ref('')
const generatedTopics = ref([])  // 选题标题列表
const selectedTopic = ref('')
const streamingTopicsText = ref('') // 流式生成选题时的实时文本
const articleContent = ref('')
const feedback = ref('')
const imageUrls = ref([])
const visualPoints = ref([])
const nodeMetrics = ref([])

// 计算属性 - 总耗时
const totalDuration = computed(() => {
  const total = nodeMetrics.value.reduce((sum, m) => sum + (m.duration_ms || 0), 0)
  return formatDuration(total)
})

// 计算属性 - 总Token
const totalTokens = computed(() => {
  return nodeMetrics.value.reduce((sum, m) => sum + (m.total_tokens || 0), 0)
})

// 格式化耗时
function formatDuration(ms) {
  if (!ms) return '0ms'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

// 获取节点显示名称
function getNodeDisplayName(nodeName) {
  const nameMap = {
    'plan_topics': '选题规划',
    'write_draft': '文章写作',
    'extract_visuals': '提取配图要点',
    'generate_images': '生成配图'
  }
  return nameMap[nodeName] || nodeName
}

// 页面加载时获取历史记录（在 checkAuth 之后）
// 已移动到 watch isLoggedIn

// 显示消息
function showMessage(msg, type = 'info') {
  message.value = msg
  messageType.value = type
  setTimeout(() => {
    message.value = ''
  }, 5000)
}

// 启动工作流 (使用 LangGraph 官方 graph.astream)
// 选题阶段使用非流式结构化输出，但通过 SSE 获取进度更新
async function handleStart() {
  if (!topicDirection.value.trim()) return
  
  loading.value = true
  message.value = ''
  generatedTopics.value = []
  streamingTopicsText.value = '' // 重置流式文本
  
  // 立即切换到步骤1，这样用户才能看到加载状态
  currentStep.value = 1
  
  try {
    // 使用官方 graph.astream 流式启动工作流
    // 选题阶段后端使用非流式结构化输出，SSE 主要用于进度反馈
    await streamStartWorkflow(topicDirection.value, {
      // 初始化：获取 thread_id
      onInit: (data) => {
        threadId.value = data.thread_id
        addStreamLog('init', data, 'start')
      },
      // 开始事件
      onStart: (data) => {
        addStreamLog('start', data, 'start')
      },
      // 节点开始事件 (events 模式)
      onNodeStart: (data) => {
        addStreamLog('node_start', data, 'start')
      },
      // 节点结束事件 (events 模式)
      onNodeEnd: (data) => {
        addStreamLog('node_end', data, 'start')
        // 节点结束时可能包含 metrics 信息
        if (data.metrics) {
          nodeMetrics.value = [...nodeMetrics.value, data.metrics]
        }
      },
      // LLM 开始事件 (events 模式)
      onLlmStart: (data) => {
        addStreamLog('llm_start', data, 'start')
      },
      // LLM token 流式输出（events 模式）- 选题阶段是结构化输出，不会有 token
      onLlmToken: (content) => {
        // 选题阶段使用结构化输出，一般不会触发此回调
        // 但保留以兼容旧行为
        addStreamLog('llm_token', content, 'start')
      },
      // LLM 结束事件 (events 模式)
      onLlmEnd: (data) => {
        addStreamLog('llm_end', data, 'start')
      },
      // 节点更新事件（updates 模式会触发）
      onUpdate: (node, output) => {
        console.log('节点更新:', node, output)
        addStreamLog('update', { node, output }, 'start')
        // 子图名称是 topic_selection，内部包含 plan_topics 节点
        // updates 模式下返回的是子图名称
        if (node === 'topic_selection' || node === 'plan_topics' || node.includes('plan_topics')) {
          if (output.generated_topics?.length > 0) {
            generatedTopics.value = output.generated_topics
          }
        }
        if (output.node_metrics) {
          nodeMetrics.value = output.node_metrics
        }
      },
      // 状态事件 (values 模式)
      onState: (data) => {
        addStreamLog('state', data, 'start')
      },
      // 完成事件
      onDone: (data) => {
        addStreamLog('done', data, 'start')
        workflowStatus.value = data.status
        fetchThreadList()
        workflowError.value = data.values?.error || ""
        interruptInfo.value = data.interrupt_info
        
        // 从 interrupt_info 中获取选题列表
        if (data.interrupt_info?.options?.length > 0 && generatedTopics.value.length === 0) {
          generatedTopics.value = data.interrupt_info.options
        }
        
        // 使用最终状态的选题列表
        if (data.values?.generated_topics?.length > 0) {
          generatedTopics.value = data.values.generated_topics
        }
        if (data.values?.node_metrics) {
          nodeMetrics.value = data.values.node_metrics
        }
        streamingTopicsText.value = ''
        loading.value = false
        showMessage('选题已生成，请选择一个继续', 'success')
        fetchThreadList()
      },
      // 错误事件
      onError: (errorMsg) => {
        workflowError.value = errorMsg
        console.error('流式启动失败:', errorMsg)
        addStreamLog('error', { message: errorMsg }, 'start')
        loading.value = false
        streamingTopicsText.value = ''
        currentStep.value = 0
        showMessage(`启动失败: ${errorMsg}`, 'error')
      }
    }, 'updates')  // 选题阶段使用 updates 模式（非流式结构化输出）
    
  } catch (error) {
    loading.value = false
    streamingTopicsText.value = ''
    currentStep.value = 0
    showMessage(`启动失败: ${error.message}`, 'error')
  }
}

// 选择选题 (使用 LangGraph 官方 graph.astream)
async function handleSelectTopic() {
  if (!selectedTopic.value) return
  
  loading.value = true
  currentStep.value = 2
  articleContent.value = ''
  
  try {
    // 使用官方 graph.astream 流式恢复工作流
    await streamSelectTopic(threadId.value, selectedTopic.value, {
      // 恢复事件
      onResume: (data) => {
        addStreamLog('resume', data, 'select_topic')
      },
      // 开始事件
      onStart: (data) => {
        addStreamLog('start', data, 'select_topic')
      },
      // 节点开始事件
      onNodeStart: (data) => {
        addStreamLog('node_start', data, 'select_topic')
      },
      // 节点结束事件
      onNodeEnd: (data) => {
        addStreamLog('node_end', data, 'select_topic')
      },
      // LLM 开始事件
      onLlmStart: (data) => {
        addStreamLog('llm_start', data, 'select_topic')
      },
      // LLM token 流式输出
      onLlmToken: (content) => {
        articleContent.value += content
        addStreamLog('llm_token', content, 'select_topic')
      },
      // LLM 结束事件
      onLlmEnd: (data) => {
        addStreamLog('llm_end', data, 'select_topic')
      },
      // 节点更新事件
      onUpdate: (node, output) => {
        console.log('节点更新:', node, output)
        addStreamLog('update', { node, output }, 'select_topic')
        if (node === 'write_draft' && output.article_content) {
          articleContent.value = output.article_content
        }
        if (output.node_metrics) {
          nodeMetrics.value = output.node_metrics
        }
      },
      // 完成事件
      onDone: (data) => {
        addStreamLog('done', data, 'select_topic')
        workflowStatus.value = data.status
        fetchThreadList()
        workflowError.value = data.values?.error || ""
        interruptInfo.value = data.interrupt_info
        // 使用最终状态的文章内容
        if (data.values?.article_content) {
          articleContent.value = data.values.article_content
        }
        if (data.values?.node_metrics) {
          nodeMetrics.value = data.values.node_metrics
        }
        loading.value = false
        showMessage('文章草稿已生成，请审核', 'success')
      },
      // 错误事件
      onError: (errorMsg) => {
        workflowError.value = errorMsg
        console.error('选题失败:', errorMsg)
        addStreamLog('error', { message: errorMsg }, 'select_topic')
        loading.value = false
        currentStep.value = 1
        showMessage(`操作失败: ${errorMsg}`, 'error')
      }
    }, 'events')
    
  } catch (error) {
    loading.value = false
    showMessage(`操作失败: ${error.message}`, 'error')
    currentStep.value = 1
  }
}

// 审核通过 (使用 LangGraph 官方 graph.astream)
async function handleApprove() {
  loading.value = true
  currentStep.value = 3
  
  try {
    await streamApproveArticle(threadId.value, {
      // 恢复事件
      onResume: (data) => {
        addStreamLog('resume', data, 'approve')
      },
      // 开始事件
      onStart: (data) => {
        addStreamLog('start', data, 'approve')
      },
      // 节点更新
      onUpdate: (node, output) => {
        console.log('节点更新:', node, output)
        addStreamLog('update', { node, output }, 'approve')
        if (output.visual_points) {
          visualPoints.value = output.visual_points
        }
        if (output.image_urls) {
          imageUrls.value = output.image_urls
        }
        if (output.node_metrics) {
          nodeMetrics.value = output.node_metrics
        }
      },
      // 完成
      onDone: (data) => {
        addStreamLog('done', data, 'approve')
        workflowStatus.value = data.status
        fetchThreadList()
        workflowError.value = data.values?.error || ""
        interruptInfo.value = data.interrupt_info || null
        if (data.is_completed || data.status === "images_failed") {
          articleContent.value = data.values?.article_content || articleContent.value
          imageUrls.value = data.values?.image_urls || []
          visualPoints.value = data.values?.visual_points || []
          if (data.values?.node_metrics) {
            nodeMetrics.value = data.values.node_metrics
          }
          currentStep.value = 4
          showMessage(data.status === 'images_failed' ? '配图未全部完成，请查看错误后重试' : '工作流已完成！', data.status === 'images_failed' ? 'error' : 'success')
        }
        loading.value = false
      },
      // 错误
      onError: (errorMsg) => {
        workflowError.value = errorMsg
        console.error('审核通过失败:', errorMsg)
        addStreamLog('error', { message: errorMsg }, 'approve')
        loading.value = false
        currentStep.value = 2
        showMessage(`操作失败: ${errorMsg}`, 'error')
      }
    }, 'updates')  // 使用 updates 模式，不需要 LLM token 流式输出
  } catch (error) {
    loading.value = false
    currentStep.value = 2
    showMessage(`操作失败: ${error.message}`, 'error')
  }
}

// 驳回重写 (使用 LangGraph 官方 graph.astream)
async function handleReject() {
  loading.value = true
  articleContent.value = ''
  const currentFeedback = feedback.value
  feedback.value = ''
  
  try {
    await streamRejectArticle(threadId.value, currentFeedback, {
      // 恢复事件
      onResume: (data) => {
        addStreamLog('resume', data, 'reject')
      },
      // 开始事件
      onStart: (data) => {
        addStreamLog('start', data, 'reject')
      },
      // 节点开始事件
      onNodeStart: (data) => {
        addStreamLog('node_start', data, 'reject')
      },
      // 节点结束事件
      onNodeEnd: (data) => {
        addStreamLog('node_end', data, 'reject')
      },
      // LLM 开始事件
      onLlmStart: (data) => {
        addStreamLog('llm_start', data, 'reject')
      },
      // LLM token 流式输出
      onLlmToken: (content) => {
        articleContent.value += content
        addStreamLog('llm_token', content, 'reject')
      },
      // LLM 结束事件
      onLlmEnd: (data) => {
        addStreamLog('llm_end', data, 'reject')
      },
      // 节点更新
      onUpdate: (node, output) => {
        console.log('节点更新:', node, output)
        addStreamLog('update', { node, output }, 'reject')
        if (node === 'write_draft' && output.article_content) {
          articleContent.value = output.article_content
        }
        if (output.node_metrics) {
          nodeMetrics.value = output.node_metrics
        }
      },
      // 完成
      onDone: (data) => {
        addStreamLog('done', data, 'reject')
        workflowStatus.value = data.status
        fetchThreadList()
        workflowError.value = data.values?.error || ""
        interruptInfo.value = data.interrupt_info
        if (data.values?.article_content) {
          articleContent.value = data.values.article_content
        }
        if (data.values?.node_metrics) {
          nodeMetrics.value = data.values.node_metrics
        }
        loading.value = false
        showMessage('文章已重写，请重新审核', 'info')
      },
      // 错误
      onError: (errorMsg) => {
        workflowError.value = errorMsg
        console.error('驳回重写失败:', errorMsg)
        addStreamLog('error', { message: errorMsg }, 'reject')
        loading.value = false
        showMessage(`操作失败: ${errorMsg}`, 'error')
      }
    }, 'events')  // 使用 events 模式获取 LLM token 流式输出
  } catch (error) {
    loading.value = false
    showMessage(`操作失败: ${error.message}`, 'error')
  }
}

async function handleRetry() {
  loading.value = true
  try {
    await retryWorkflow(threadId.value)
    await handleSwitchThread(threadId.value)
    await fetchThreadList()
  } catch (error) {
    showMessage(error.response?.data?.detail || error.message, 'error')
  } finally {
    loading.value = false
  }
}

// 重置
function handleReset() {
  currentStep.value = 0
  threadId.value = ''
  workflowStatus.value = ''
  workflowError.value = ""
  interruptInfo.value = null
  topicDirection.value = ''
  generatedTopics.value = []
  selectedTopic.value = ''
  streamingTopicsText.value = ''
  articleContent.value = ''
  feedback.value = ''
  imageUrls.value = []
  visualPoints.value = []
  nodeMetrics.value = []
  message.value = ''
  streamLogs.value = []  // 清空流式日志
}

// 新建工作流
function handleNewWorkflow() {
  handleReset()
  fetchThreadList()
}

// 获取历史记录列表
async function fetchThreadList() {
  loadingThreads.value = true
  try {
    const result = await getAllThreads()
    threadList.value = result.threads || []
  } catch (error) {
    console.error('获取历史记录失败:', error)
  } finally {
    loadingThreads.value = false
  }
}

// 切换到指定的工作流
async function handleSwitchThread(targetThreadId) {
  // Reloading the current thread is also allowed after retry.
  
  loading.value = true
  message.value = ''
  
  try {
    const state = await getWorkflowState(targetThreadId)
    
    // 更新状态
    threadId.value = targetThreadId
    workflowStatus.value = state.status
    workflowError.value = state.values?.error || ""
    interruptInfo.value = state.interrupt_info
    
    // 更新数据
    const values = state.values || {}
    topicDirection.value = values.topic_direction || ''
    generatedTopics.value = values.generated_topics || []
    selectedTopic.value = values.selected_topic || ''
    articleContent.value = values.article_content || ''
    imageUrls.value = values.image_urls || []
    visualPoints.value = values.visual_points || []
    feedback.value = ''
    
    // 清空临时状态
    streamingTopicsText.value = ''
    streamLogs.value = []  // 清空流式日志
    
    // 从 state.node_metrics 或 values.node_metrics 获取指标
    // 注意：后端返回的 node_metrics 可能是 NodeMetricInfo 对象数组
    const rawMetrics = state.node_metrics || values.node_metrics || []
    // 确保转换为普通对象数组
    nodeMetrics.value = rawMetrics.map(m => ({
      node_name: m.node_name || '',
      duration_ms: m.duration_ms || 0,
      input_tokens: m.input_tokens || 0,
      output_tokens: m.output_tokens || 0,
      total_tokens: m.total_tokens || 0,
      start_time: m.start_time || '',
      end_time: m.end_time || '',
      model: m.model || ''
    }))
    
    // 根据状态判断当前步骤
    currentStep.value = determineCurrentStep(state)
    
    if (values.error) showMessage(values.error, 'error')
    else showMessage('工作流状态已恢复', 'success')
  } catch (error) {
    showMessage(`切换失败: ${error.response?.data?.detail || error.message}`, 'error')
  } finally {
    loading.value = false
  }
}

// 根据状态判断当前步骤
function determineCurrentStep(state) {
  const values = state.values || {}
  const interruptInfo = state.interrupt_info
  const isCompleted = state.is_completed
  
  // 已完成
  if (isCompleted || state.status === "images_failed") {
    return 4
  }
  
  // 根据中断信息判断
  if (interruptInfo) {
    const actionRequired = interruptInfo.action_required
    if (actionRequired === 'select_topic') {
      return 1 // 选择选题阶段
    } else if (actionRequired === 'review') {
      return 2 // 审核文章阶段
    }
  }
  
  // 根据数据判断
  if (values.image_urls && values.image_urls.length > 0) {
    return 4 // 已完成
  }
  if (values.article_content) {
    return 2 // 审核阶段
  }
  if (values.generated_topics && values.generated_topics.length > 0) {
    return 1 // 选题阶段
  }
  
  return 0 // 初始阶段
}

// 删除工作流
async function handleDeleteThread(targetThreadId) {
  if (!confirm('确定要删除这条历史记录吗？')) return
  
  try {
    await deleteThread(targetThreadId)
    
    // 如果删除的是当前工作流，重置状态
    if (targetThreadId === threadId.value) {
      handleReset()
    }
    
    // 刷新列表
    await fetchThreadList()
    showMessage('删除成功', 'success')
  } catch (error) {
    showMessage(`删除失败: ${error.response?.data?.detail || error.message}`, 'error')
  }
}
</script>
