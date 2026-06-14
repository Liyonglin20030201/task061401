<template>
  <div class="chat-container">
    <div class="chat-sidebar">
      <el-select v-model="selectedKb" placeholder="选择知识库" @change="loadConversations" style="width: 100%; margin-bottom: 12px;">
        <el-option v-for="kb in knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id" />
      </el-select>
      <el-button type="primary" @click="newConversation" style="width: 100%; margin-bottom: 12px;">新建对话</el-button>
      <div class="conversation-list">
        <div
          v-for="conv in conversations"
          :key="conv.id"
          class="conv-item"
          :class="{ active: conv.id === currentConvId }"
          @click="selectConversation(conv.id)"
        >
          {{ conv.title }}
        </div>
      </div>
    </div>

    <div class="chat-main">
      <div class="messages" ref="messagesContainer">
        <div v-for="msg in messages" :key="msg.id" class="message" :class="msg.role">
          <div class="message-content">
            <div class="message-text" v-html="renderMarkdown(msg.content)"></div>
            <div v-if="msg.citations?.length" class="citations">
              <el-tag v-for="(cite, i) in msg.citations" :key="i" size="small" type="info" class="cite-tag">
                [{{ i + 1 }}] {{ cite.document_title }} (相似度: {{ (cite.score * 100).toFixed(1) }}%)
              </el-tag>
            </div>
            <div class="message-actions" v-if="msg.role === 'assistant'">
              <el-button size="small" text @click="openCorrection(msg)">纠错</el-button>
              <el-button size="small" text @click="openFeedback(msg)">评分</el-button>
            </div>
          </div>
        </div>
        <div v-if="streaming" class="message assistant">
          <div class="message-content">
            <div class="message-text" v-html="renderMarkdown(streamingText)"></div>
            <span class="typing-indicator">...</span>
          </div>
        </div>
      </div>

      <div class="input-area">
        <el-input
          v-model="inputMessage"
          type="textarea"
          :rows="2"
          placeholder="输入您的问题..."
          @keydown.enter.ctrl="sendMessage"
        />
        <el-button type="primary" @click="sendMessage" :disabled="!inputMessage.trim() || !selectedKb || streaming">
          发送 (Ctrl+Enter)
        </el-button>
      </div>
    </div>

    <!-- Correction Dialog -->
    <el-dialog v-model="correctionVisible" title="人工纠错">
      <el-input v-model="correctionText" type="textarea" :rows="4" placeholder="请输入正确答案" />
      <template #footer>
        <el-button @click="correctionVisible = false">取消</el-button>
        <el-button type="primary" @click="submitCorrection">提交纠错</el-button>
      </template>
    </el-dialog>

    <!-- Feedback Dialog -->
    <el-dialog v-model="feedbackVisible" title="回答评分">
      <el-rate v-model="feedbackRating" :max="5" show-text :texts="['很差', '较差', '一般', '较好', '很好']" />
      <el-input v-model="feedbackComment" type="textarea" :rows="2" placeholder="补充评价（可选）" style="margin-top: 12px;" />
      <template #footer>
        <el-button @click="feedbackVisible = false">取消</el-button>
        <el-button type="primary" @click="submitFeedback">提交评分</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt()

interface KnowledgeBase { id: string; name: string }
interface Conversation { id: string; title: string }
interface Message { id: string; role: string; content: string; citations?: any[] }

const knowledgeBases = ref<KnowledgeBase[]>([])
const selectedKb = ref('')
const conversations = ref<Conversation[]>([])
const currentConvId = ref<string | null>(null)
const messages = ref<Message[]>([])
const inputMessage = ref('')
const streaming = ref(false)
const streamingText = ref('')
const messagesContainer = ref<HTMLElement | null>(null)

const correctionVisible = ref(false)
const correctionText = ref('')
const correctionMsgId = ref('')

const feedbackVisible = ref(false)
const feedbackRating = ref(3)
const feedbackComment = ref('')
const feedbackMsgId = ref('')

function renderMarkdown(text: string) {
  return md.render(text)
}

onMounted(async () => {
  const res = await api.get('/kb')
  knowledgeBases.value = res.data
  if (knowledgeBases.value.length > 0) {
    selectedKb.value = knowledgeBases.value[0].id
    await loadConversations()
  }
})

async function loadConversations() {
  const res = await api.get('/chat/conversations')
  conversations.value = res.data.filter((c: any) => c.kb_id === selectedKb.value)
}

function newConversation() {
  currentConvId.value = null
  messages.value = []
}

async function selectConversation(id: string) {
  currentConvId.value = id
  const res = await api.get(`/chat/conversations/${id}`)
  messages.value = res.data
}

async function sendMessage() {
  if (!inputMessage.value.trim() || !selectedKb.value || streaming.value) return

  const userMessage = inputMessage.value.trim()
  inputMessage.value = ''
  messages.value.push({ id: Date.now().toString(), role: 'user', content: userMessage })

  streaming.value = true
  streamingText.value = ''

  try {
    const response = await fetch('/api/chat/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
      },
      body: JSON.stringify({
        message: userMessage,
        kb_id: selectedKb.value,
        conversation_id: currentConvId.value,
      }),
    })

    if (!response.ok) {
      const err = await response.json()
      ElMessage.error(err.detail || '请求失败')
      streaming.value = false
      return
    }

    const contentType = response.headers.get('content-type') || ''

    if (contentType.includes('text/event-stream')) {
      const reader = response.body!.getReader()
      const decoder = new TextDecoder()

      let citations: any[] = []
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const text = decoder.decode(value)
        const lines = text.split('\n')
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6))
            if (data.token) {
              streamingText.value += data.token
            }
            if (data.done) {
              citations = data.citations || []
              if (data.conversation_id) {
                currentConvId.value = data.conversation_id
              }
            }
          }
        }
        await nextTick()
        scrollToBottom()
      }

      messages.value.push({
        id: Date.now().toString(),
        role: 'assistant',
        content: streamingText.value,
        citations,
      })
    } else {
      const data = await response.json()
      messages.value.push({
        id: Date.now().toString(),
        role: 'assistant',
        content: data.message,
        citations: data.citations || [],
      })
      if (data.conversation_id) {
        currentConvId.value = data.conversation_id
      }
    }
  } catch (e: any) {
    ElMessage.error('发送消息失败')
  } finally {
    streaming.value = false
    streamingText.value = ''
    scrollToBottom()
  }
}

function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

function openCorrection(msg: Message) {
  correctionMsgId.value = msg.id
  correctionText.value = ''
  correctionVisible.value = true
}

async function submitCorrection() {
  try {
    await api.put(`/chat/messages/${correctionMsgId.value}/correct`, {
      corrected_content: correctionText.value,
    })
    ElMessage.success('纠错提交成功')
    correctionVisible.value = false
  } catch {
    ElMessage.error('提交失败')
  }
}

function openFeedback(msg: Message) {
  feedbackMsgId.value = msg.id
  feedbackRating.value = 3
  feedbackComment.value = ''
  feedbackVisible.value = true
}

async function submitFeedback() {
  try {
    await api.post('/feedback/', {
      message_id: feedbackMsgId.value,
      rating: feedbackRating.value,
      comment: feedbackComment.value,
    })
    ElMessage.success('评分提交成功')
    feedbackVisible.value = false
  } catch {
    ElMessage.error('提交失败')
  }
}
</script>

<style scoped>
.chat-container {
  display: flex;
  height: calc(100vh - 120px);
  gap: 16px;
}
.chat-sidebar {
  width: 250px;
  padding: 12px;
  background: #fff;
  border-radius: 8px;
  overflow-y: auto;
}
.conversation-list {
  overflow-y: auto;
}
.conv-item {
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-item:hover { background: #f0f2f5; }
.conv-item.active { background: #e6f7ff; color: #1890ff; }
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 8px;
  padding: 16px;
}
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px 0;
}
.message {
  margin-bottom: 16px;
  display: flex;
}
.message.user { justify-content: flex-end; }
.message.assistant { justify-content: flex-start; }
.message-content {
  max-width: 70%;
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
}
.message.user .message-content {
  background: #1890ff;
  color: #fff;
}
.message.assistant .message-content {
  background: #f5f5f5;
  color: #333;
}
.citations {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.cite-tag { cursor: pointer; }
.message-actions {
  margin-top: 6px;
  display: flex;
  gap: 4px;
}
.typing-indicator {
  animation: blink 1s infinite;
}
@keyframes blink {
  50% { opacity: 0; }
}
.input-area {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  border-top: 1px solid #e6e6e6;
  padding-top: 12px;
}
.input-area .el-input { flex: 1; }
</style>
