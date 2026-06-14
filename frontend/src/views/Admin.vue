<template>
  <div class="admin-page">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="系统概览" name="dashboard">
        <el-row :gutter="16" v-if="stats">
          <el-col :span="6">
            <el-card shadow="hover"><el-statistic title="总用户数" :value="stats.total_users" /></el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover"><el-statistic title="总文档数" :value="stats.total_documents" /></el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover"><el-statistic title="总对话数" :value="stats.total_conversations" /></el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover"><el-statistic title="平均评分" :value="stats.avg_rating" :precision="2" /></el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <el-tab-pane label="用户管理" name="users">
        <el-table :data="users" stripe>
          <el-table-column prop="username" label="用户名" />
          <el-table-column prop="email" label="邮箱" />
          <el-table-column prop="role" label="角色" width="120">
            <template #default="{ row }">
              <el-select :model-value="row.role" @change="(val: string) => updateRole(row.id, val)" size="small">
                <el-option label="管理员" value="admin" />
                <el-option label="编辑者" value="editor" />
                <el-option label="查看者" value="viewer" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column prop="is_active" label="状态" width="100">
            <template #default="{ row }">
              <el-switch :model-value="row.is_active" @change="(val: boolean) => updateStatus(row.id, val)" />
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="敏感词管理" name="sensitive">
        <div style="margin-bottom: 16px;">
          <el-input v-model="newWord" placeholder="新增敏感词" style="width: 200px; margin-right: 8px;" />
          <el-input v-model="newWordCategory" placeholder="分类" style="width: 120px; margin-right: 8px;" />
          <el-button type="primary" @click="addWord">添加</el-button>
        </div>
        <el-table :data="sensitiveWords" stripe>
          <el-table-column prop="word" label="敏感词" />
          <el-table-column prop="category" label="分类" width="120" />
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button size="small" text type="danger" @click="removeWord(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="反馈统计" name="feedback">
        <el-card v-if="feedbackStats">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="总反馈数">{{ feedbackStats.total_feedback }}</el-descriptions-item>
            <el-descriptions-item label="平均评分">{{ feedbackStats.average_rating }}</el-descriptions-item>
          </el-descriptions>
          <h4 style="margin-top: 16px;">评分分布</h4>
          <div v-for="(count, rating) in feedbackStats.rating_distribution" :key="rating" style="margin: 4px 0;">
            {{ rating }}星: {{ count }}条
            <el-progress :percentage="feedbackStats.total_feedback ? (count / feedbackStats.total_feedback * 100) : 0" :show-text="false" style="display: inline-block; width: 200px; margin-left: 8px;" />
          </div>
          <h4 style="margin-top: 16px;">近期差评</h4>
          <el-table :data="feedbackStats.recent_negative" stripe size="small">
            <el-table-column prop="rating" label="评分" width="60" />
            <el-table-column prop="comment" label="评价" />
            <el-table-column prop="created_at" label="时间" width="180" />
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="系统配置" name="config">
        <el-form label-width="160px" style="max-width: 500px;">
          <el-form-item v-for="(value, key) in systemConfig" :key="key" :label="configLabels[key] || key">
            <el-input :model-value="JSON.stringify(value)" @change="(val: string) => updateConfig(key, val)" />
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'

const activeTab = ref('dashboard')
const stats = ref<any>(null)
const users = ref<any[]>([])
const sensitiveWords = ref<any[]>([])
const feedbackStats = ref<any>(null)
const systemConfig = ref<Record<string, any>>({})
const newWord = ref('')
const newWordCategory = ref('general')

const configLabels: Record<string, string> = {
  chunk_size: '切片大小（tokens）',
  chunk_overlap: '切片重叠（tokens）',
  similarity_threshold: '相似度阈值',
  max_retrieval_count: '最大检索数量',
  chat_model: '对话模型',
  embedding_model: '嵌入模型',
}

onMounted(async () => {
  await Promise.all([loadStats(), loadUsers(), loadWords(), loadFeedback(), loadConfig()])
})

async function loadStats() {
  const res = await api.get('/admin/stats/dashboard')
  stats.value = res.data
}

async function loadUsers() {
  const res = await api.get('/admin/users')
  users.value = res.data
}

async function loadWords() {
  const res = await api.get('/admin/config/sensitive-words')
  sensitiveWords.value = res.data
}

async function loadFeedback() {
  const res = await api.get('/feedback/stats')
  feedbackStats.value = res.data
}

async function loadConfig() {
  const res = await api.get('/admin/config/system')
  systemConfig.value = res.data
}

async function updateRole(userId: string, role: string) {
  await api.put(`/admin/users/${userId}/role`, null, { params: { role } })
  ElMessage.success('角色已更新')
  await loadUsers()
}

async function updateStatus(userId: string, isActive: boolean) {
  await api.put(`/admin/users/${userId}/status`, null, { params: { is_active: isActive } })
  ElMessage.success('状态已更新')
}

async function addWord() {
  if (!newWord.value) return
  await api.post('/admin/config/sensitive-words', { word: newWord.value, category: newWordCategory.value })
  ElMessage.success('已添加')
  newWord.value = ''
  await loadWords()
}

async function removeWord(id: number) {
  await api.delete(`/admin/config/sensitive-words/${id}`)
  ElMessage.success('已删除')
  await loadWords()
}

async function updateConfig(key: string, val: string) {
  try {
    const value = JSON.parse(val)
    await api.put('/admin/config/system', { key, value: { value } })
    ElMessage.success('配置已更新')
  } catch {
    ElMessage.error('请输入有效的JSON值')
  }
}
</script>

<style scoped>
.admin-page {
  padding: 16px;
}
.el-row {
  margin-bottom: 20px;
}
</style>
