<template>
  <div class="documents-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>文档管理</span>
          <div>
            <el-select v-model="selectedKb" placeholder="选择知识库" @change="loadDocuments" style="margin-right: 12px;">
              <el-option v-for="kb in knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id" />
            </el-select>
            <el-button type="primary" @click="showUpload = true">上传文档</el-button>
            <el-button @click="showCreateKb = true">新建知识库</el-button>
          </div>
        </div>
      </template>

      <el-table :data="documents" v-loading="loading" stripe>
        <el-table-column prop="title" label="标题" />
        <el-table-column prop="file_type" label="类型" width="80">
          <template #default="{ row }">
            <el-tag size="small">{{ row.file_type.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusColor(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="60" />
        <el-table-column prop="created_at" label="上传时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button size="small" text @click="refreshDoc(row.id)">刷新状态</el-button>
            <el-button size="small" text type="danger" @click="deleteDoc(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Upload Dialog -->
    <el-dialog v-model="showUpload" title="上传文档" width="500px">
      <el-form label-position="top">
        <el-form-item label="文档标题">
          <el-input v-model="uploadTitle" placeholder="输入文档标题" />
        </el-form-item>
        <el-form-item label="选择文件">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            accept=".pdf,.docx,.md"
            :on-change="handleFileChange"
          >
            <el-button>选择文件 (PDF/DOCX/MD)</el-button>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUpload = false">取消</el-button>
        <el-button type="primary" @click="handleUpload" :loading="uploading">上传</el-button>
      </template>
    </el-dialog>

    <!-- Create KB Dialog -->
    <el-dialog v-model="showCreateKb" title="新建知识库" width="400px">
      <el-form label-position="top">
        <el-form-item label="名称">
          <el-input v-model="newKbName" placeholder="知识库名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="newKbDesc" type="textarea" placeholder="描述（可选）" />
        </el-form-item>
        <el-form-item label="访问级别">
          <el-select v-model="newKbAccess" style="width: 100%;">
            <el-option label="公开" value="public" />
            <el-option label="内部" value="internal" />
            <el-option label="受限" value="restricted" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateKb = false">取消</el-button>
        <el-button type="primary" @click="createKb">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const knowledgeBases = ref<any[]>([])
const selectedKb = ref('')
const documents = ref<any[]>([])
const loading = ref(false)

const showUpload = ref(false)
const uploadTitle = ref('')
const uploadFile = ref<File | null>(null)
const uploading = ref(false)

const showCreateKb = ref(false)
const newKbName = ref('')
const newKbDesc = ref('')
const newKbAccess = ref('internal')

onMounted(async () => {
  const res = await api.get('/kb')
  knowledgeBases.value = res.data
  if (knowledgeBases.value.length > 0) {
    selectedKb.value = knowledgeBases.value[0].id
    await loadDocuments()
  }
})

async function loadDocuments() {
  if (!selectedKb.value) return
  loading.value = true
  try {
    const res = await api.get('/documents', { params: { kb_id: selectedKb.value } })
    documents.value = res.data
  } finally {
    loading.value = false
  }
}

function handleFileChange(file: any) {
  uploadFile.value = file.raw
}

async function handleUpload() {
  if (!uploadFile.value || !uploadTitle.value) {
    ElMessage.warning('请填写标题并选择文件')
    return
  }
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', uploadFile.value)
    formData.append('title', uploadTitle.value)
    formData.append('kb_id', selectedKb.value)
    await api.post('/documents/upload', formData)
    ElMessage.success('上传成功，正在处理中...')
    showUpload.value = false
    uploadTitle.value = ''
    uploadFile.value = null
    await loadDocuments()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

async function refreshDoc(docId: string) {
  const res = await api.get(`/documents/${docId}/status`)
  const doc = documents.value.find(d => d.id === docId)
  if (doc) doc.status = res.data.status
}

async function deleteDoc(docId: string) {
  await ElMessageBox.confirm('确定删除该文档？', '确认')
  await api.delete(`/documents/${docId}`)
  ElMessage.success('删除成功')
  await loadDocuments()
}

async function createKb() {
  try {
    await api.post('/kb', { name: newKbName.value, description: newKbDesc.value, access_level: newKbAccess.value })
    ElMessage.success('知识库创建成功')
    showCreateKb.value = false
    const res = await api.get('/kb')
    knowledgeBases.value = res.data
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '创建失败')
  }
}

function statusColor(status: string) {
  const map: Record<string, string> = { ready: 'success', processing: 'warning', pending: 'info', error: 'danger' }
  return map[status] || 'info'
}

function statusText(status: string) {
  const map: Record<string, string> = { ready: '就绪', processing: '处理中', pending: '等待中', error: '错误' }
  return map[status] || status
}

function formatTime(t: string) {
  return new Date(t).toLocaleString('zh-CN')
}
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
