<template>
  <div class="analytics-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>问答数据分析</span>
          <div class="filters">
            <el-select v-model="selectedKb" placeholder="全部知识库" clearable style="width: 180px; margin-right: 12px;">
              <el-option v-for="kb in knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id" />
            </el-select>
            <el-select v-model="days" style="width: 120px; margin-right: 12px;">
              <el-option label="近7天" :value="7" />
              <el-option label="近30天" :value="30" />
              <el-option label="近90天" :value="90" />
            </el-select>
            <el-button @click="loadAll">刷新</el-button>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeTab">
        <el-tab-pane label="高频问题" name="questions">
          <div style="margin-bottom: 12px;">
            <el-button type="primary" size="small" @click="triggerClustering" :loading="clustering">
              重新聚类分析
            </el-button>
          </div>
          <el-table :data="topQuestions" stripe v-loading="loadingQuestions">
            <el-table-column prop="representative_question" label="典型问题" min-width="300" show-overflow-tooltip />
            <el-table-column prop="question_count" label="出现次数" width="100" sortable />
            <el-table-column label="平均评分" width="100">
              <template #default="{ row }">{{ row.avg_rating ? row.avg_rating.toFixed(1) : '-' }}</template>
            </el-table-column>
            <el-table-column label="平均置信度" width="120">
              <template #default="{ row }">{{ row.avg_confidence ? (row.avg_confidence * 100).toFixed(1) + '%' : '-' }}</template>
            </el-table-column>
            <el-table-column label="最近提问" width="180">
              <template #default="{ row }">{{ formatTime(row.last_asked_at) }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="满意度趋势" name="satisfaction">
          <div v-if="satisfactionTrend.length" class="trend-chart">
            <div v-for="point in satisfactionTrend" :key="point.date" class="trend-bar">
              <div class="trend-label">{{ point.date.slice(5) }}</div>
              <div class="trend-bar-container">
                <div class="trend-bar-fill" :style="{ width: (point.avg_rating / 5 * 100) + '%' }" />
              </div>
              <div class="trend-value">{{ point.avg_rating.toFixed(1) }} ({{ point.total_feedback }}条)</div>
            </div>
          </div>
          <el-empty v-else description="暂无反馈数据" />
        </el-tab-pane>

        <el-tab-pane label="回答准确率" name="accuracy">
          <el-row :gutter="16" v-if="accuracy" style="margin-bottom: 20px;">
            <el-col :span="6">
              <el-card shadow="hover"><el-statistic title="总回答数" :value="accuracy.total_questions" /></el-card>
            </el-col>
            <el-col :span="6">
              <el-card shadow="hover"><el-statistic title="高置信回答" :value="accuracy.high_confidence_count" /></el-card>
            </el-col>
            <el-col :span="6">
              <el-card shadow="hover"><el-statistic title="低置信回答" :value="accuracy.low_confidence_count" /></el-card>
            </el-col>
            <el-col :span="6">
              <el-card shadow="hover">
                <el-statistic title="平均置信度" :value="(accuracy.avg_confidence * 100).toFixed(1) + '%'" />
              </el-card>
            </el-col>
          </el-row>
          <div v-if="accuracy?.confidence_over_time?.length" class="trend-chart">
            <div v-for="point in accuracy.confidence_over_time" :key="point.date" class="trend-bar">
              <div class="trend-label">{{ point.date.slice(5) }}</div>
              <div class="trend-bar-container">
                <div class="trend-bar-fill confidence" :style="{ width: (point.avg_confidence * 100) + '%' }" />
              </div>
              <div class="trend-value">{{ (point.avg_confidence * 100).toFixed(1) }}%</div>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane label="知识短板" name="gaps">
          <el-table :data="knowledgeGaps" stripe v-loading="loadingGaps">
            <el-table-column prop="question" label="问题内容" min-width="300" show-overflow-tooltip />
            <el-table-column label="置信度" width="100">
              <template #default="{ row }">
                <el-tag :type="row.confidence_score < 0.5 ? 'danger' : 'warning'" size="small">
                  {{ (row.confidence_score * 100).toFixed(0) }}%
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="用户评分" width="100">
              <template #default="{ row }">{{ row.avg_rating ? row.avg_rating.toFixed(1) : '-' }}</template>
            </el-table-column>
            <el-table-column label="时间" width="180">
              <template #default="{ row }">{{ formatTime(row.last_asked_at) }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'

const activeTab = ref('questions')
const selectedKb = ref('')
const days = ref(30)
const knowledgeBases = ref<any[]>([])

const topQuestions = ref<any[]>([])
const satisfactionTrend = ref<any[]>([])
const accuracy = ref<any>(null)
const knowledgeGaps = ref<any[]>([])
const loadingQuestions = ref(false)
const loadingGaps = ref(false)
const clustering = ref(false)

onMounted(async () => {
  const res = await api.get('/kb')
  knowledgeBases.value = res.data
  await loadAll()
})

watch([selectedKb, days], () => loadAll())

async function loadAll() {
  const params: Record<string, any> = { days: days.value }
  if (selectedKb.value) params.kb_id = selectedKb.value

  await Promise.all([
    loadTopQuestions(params),
    loadSatisfaction(params),
    loadAccuracy(params),
    loadGaps(params),
  ])
}

async function loadTopQuestions(params: any) {
  loadingQuestions.value = true
  try {
    const res = await api.get('/analytics/top-questions', { params })
    topQuestions.value = res.data
  } catch { topQuestions.value = [] }
  finally { loadingQuestions.value = false }
}

async function loadSatisfaction(params: any) {
  try {
    const res = await api.get('/analytics/satisfaction-trend', { params })
    satisfactionTrend.value = res.data.data
  } catch { satisfactionTrend.value = [] }
}

async function loadAccuracy(params: any) {
  try {
    const res = await api.get('/analytics/accuracy', { params })
    accuracy.value = res.data
  } catch { accuracy.value = null }
}

async function loadGaps(params: any) {
  loadingGaps.value = true
  try {
    const res = await api.get('/analytics/knowledge-gaps', { params })
    knowledgeGaps.value = res.data
  } catch { knowledgeGaps.value = [] }
  finally { loadingGaps.value = false }
}

async function triggerClustering() {
  clustering.value = true
  try {
    const params: Record<string, any> = {}
    if (selectedKb.value) params.kb_id = selectedKb.value
    await api.post('/analytics/cluster-questions', null, { params })
    ElMessage.success('聚类分析已启动，稍后刷新查看结果')
  } catch {
    ElMessage.error('启动聚类失败')
  } finally {
    clustering.value = false
  }
}

function formatTime(t: string) {
  return new Date(t).toLocaleString('zh-CN')
}
</script>

<style scoped>
.analytics-page { padding: 16px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.filters { display: flex; align-items: center; }
.trend-chart { max-height: 400px; overflow-y: auto; }
.trend-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.trend-label { width: 50px; font-size: 12px; color: #606266; text-align: right; }
.trend-bar-container { flex: 1; height: 20px; background: #f0f2f5; border-radius: 4px; overflow: hidden; }
.trend-bar-fill { height: 100%; background: #409eff; border-radius: 4px; transition: width 0.3s; }
.trend-bar-fill.confidence { background: #67c23a; }
.trend-value { width: 100px; font-size: 12px; color: #606266; }
.el-row { margin-bottom: 20px; }
</style>
