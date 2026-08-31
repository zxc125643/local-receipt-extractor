<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { PosterCanvas } from './editor/posterCanvas'
import { createPage, createProject, createSlot, STYLE_PRESETS } from './editor/template'
import { deleteDraft, listDrafts, loadDraft, migrateDataUrlAsset, renderPage, saveDraft } from './services/api'
import { processAndUploadImage } from './services/imagePipeline'
import type { Asset, PosterStyle, Project } from './types'

const canvasElement = ref<HTMLCanvasElement | null>(null)
const canvasHost = ref<HTMLElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const project = ref<Project>(createProject())
const selectedSlotId = ref(project.value.pages[0].slots[0].id)
const saveState = ref('尚未修改')
const saveKind = ref<'normal' | 'saved' | 'error'>('normal')
const dirty = ref(false)
const revision = ref(0)
const saving = ref(false)
const pendingSave = ref(false)
const importing = ref(false)
const exporting = ref(false)
const importProgress = ref('')
const showProjects = ref(false)
const showSettings = ref(false)
const showInspector = ref(false)
const cropMode = ref(false)
const showAdvancedStyle = ref(false)
const canUndo = ref(false)
const canRedo = ref(false)
const draftItems = ref<Awaited<ReturnType<typeof listDrafts>>>([])
const draftLoading = ref(false)
const toastText = ref('')
const toastError = ref(false)
let toastTimer: ReturnType<typeof setTimeout> | undefined
let saveTimer: ReturnType<typeof setTimeout> | undefined
let renderFrame = 0
let resizeObserver: ResizeObserver | undefined
let editor: PosterCanvas | undefined
let historyCurrent = JSON.stringify(project.value)
let historyTimer: ReturnType<typeof setTimeout> | undefined
let historyGroupOpen = false
const undoStack: string[] = []
const redoStack: string[] = []

const activePage = computed(() => project.value.pages.find((page) => page.id === project.value.activePageId) || project.value.pages[0])
const selectedSlot = computed(() => activePage.value.slots.find((slot) => slot.id === selectedSlotId.value) || activePage.value.slots[0])
const styleEntries = Object.entries(STYLE_PRESETS)
const placedCount = computed(() => activePage.value.slots.filter((slot) => slot.src).length)

function updateHistoryButtons() {
  canUndo.value = undoStack.length > 0
  canRedo.value = redoStack.length > 0
}

function closeHistoryGroup() {
  clearTimeout(historyTimer)
  historyCurrent = JSON.stringify(project.value)
  historyGroupOpen = false
  updateHistoryButtons()
}

function resetHistory() {
  undoStack.length = 0
  redoStack.length = 0
  historyCurrent = JSON.stringify(project.value)
  historyGroupOpen = false
  updateHistoryButtons()
}

function toast(message: string, error = false) {
  toastText.value = message
  toastError.value = error
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toastText.value = '' }, 3200)
}

function queueRender() {
  cancelAnimationFrame(renderFrame)
  renderFrame = requestAnimationFrame(() => editor?.render(activePage.value, selectedSlotId.value))
}

function markDirty() {
  if (!historyGroupOpen) {
    undoStack.push(historyCurrent)
    if (undoStack.length > 40) undoStack.shift()
    redoStack.length = 0
    historyGroupOpen = true
  }
  clearTimeout(historyTimer)
  historyTimer = setTimeout(closeHistoryGroup, 550)
  updateHistoryButtons()
  dirty.value = true
  revision.value += 1
  saveKind.value = 'normal'
  saveState.value = '有未保存修改'
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => persist(true), 1600)
}

function restoreSnapshot(snapshot: string) {
  project.value = JSON.parse(snapshot) as Project
  selectedSlotId.value = activePage.value.slots[0].id
  dirty.value = true
  revision.value += 1
  saveState.value = '有未保存修改'
  saveKind.value = 'normal'
  queueRender()
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => persist(true), 1200)
}

function undo() {
  if (!undoStack.length) return
  closeHistoryGroup()
  redoStack.push(JSON.stringify(project.value))
  restoreSnapshot(undoStack.pop()!)
  historyCurrent = JSON.stringify(project.value)
  updateHistoryButtons()
}

function redo() {
  if (!redoStack.length) return
  closeHistoryGroup()
  undoStack.push(JSON.stringify(project.value))
  restoreSnapshot(redoStack.pop()!)
  historyCurrent = JSON.stringify(project.value)
  updateHistoryButtons()
}

function updateVisual() {
  markDirty()
  queueRender()
}

async function ensureRemoteAssets() {
  for (let index = 0; index < project.value.assets.length; index += 1) {
    const oldAsset = project.value.assets[index]
    if (!oldAsset.src.startsWith('data:')) continue
    const migrated = await migrateDataUrlAsset(oldAsset)
    migrated.originalSrc = migrated.src
    project.value.assets[index] = migrated
    for (const page of project.value.pages) {
      for (const slot of page.slots) {
        if (slot.assetId === oldAsset.id || slot.src === oldAsset.src) {
          slot.assetId = migrated.id
          slot.src = migrated.src
          slot.originalSrc = migrated.src
        }
      }
    }
  }
}

async function persist(automatic = false) {
  if (automatic && !dirty.value) return
  if (saving.value) {
    pendingSave.value = true
    return
  }
  clearTimeout(saveTimer)
  saving.value = true
  pendingSave.value = false
  const savingRevision = revision.value
  saveState.value = automatic ? '自动保存中…' : '保存中…'
  try {
    await ensureRemoteAssets()
    const result = await saveDraft(project.value)
    project.value.id = result.id
    if (revision.value === savingRevision) dirty.value = false
    saveKind.value = 'saved'
    saveState.value = `${automatic ? '✓ 已自动保存' : '✓ 保存成功'} ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
    if (!automatic) toast('项目已保存到后台素材库')
  } catch (error) {
    dirty.value = true
    saveKind.value = 'error'
    saveState.value = automatic ? '自动保存失败' : '保存失败'
    toast(error instanceof Error ? error.message : '保存失败', true)
  } finally {
    saving.value = false
  }
  if (pendingSave.value || dirty.value) {
    pendingSave.value = false
    clearTimeout(saveTimer)
    saveTimer = setTimeout(() => persist(true), 1000)
  }
}

async function importFiles(files: FileList | null) {
  const images = Array.from(files || []).filter((file) => file.type.startsWith('image/'))
  if (!images.length) return
  importing.value = true
  let success = 0
  for (let index = 0; index < images.length; index += 1) {
    importProgress.value = `正在导入 ${index + 1} / ${images.length}`
    try {
      const asset = await processAndUploadImage(images[index])
      if (!project.value.assets.some((item) => item.id === asset.id)) project.value.assets.push(asset)
      success += 1
    } catch (error) {
      toast(`${images[index].name}：${error instanceof Error ? error.message : '导入失败'}`, true)
    }
  }
  importing.value = false
  importProgress.value = `已导入 ${success} 张，素材库共 ${project.value.assets.length} 张`
  if (success) markDirty()
  if (fileInput.value) fileInput.value.value = ''
}

function useAsset(asset: Asset) {
  const slot = selectedSlot.value || activePage.value.slots.find((item) => !item.src)
  if (!slot) return toast('当前画布没有可用格子', true)
  slot.assetId = asset.id
  slot.src = asset.src
  slot.originalSrc = asset.originalSrc || asset.src
  slot.cropX = 0.5
  slot.cropY = 0.5
  slot.zoom = 1
  slot.imageLeft = undefined
  slot.imageTop = undefined
  slot.imageScale = undefined
  selectedSlotId.value = slot.id
  updateVisual()
  toast(`已放入第 ${activePage.value.slots.indexOf(slot) + 1} 格`)
}

function assetUsage(asset: Asset) {
  const current = activePage.value.slots.filter((slot) => slot.assetId === asset.id || slot.src === asset.src).length
  const total = project.value.pages.reduce((sum, page) => sum + page.slots.filter((slot) => slot.assetId === asset.id || slot.src === asset.src).length, 0)
  return current ? `本页已用${current > 1 ? ` ${current}次` : ''}` : total ? '其他页已用' : '未使用'
}

function assetClass(asset: Asset) {
  const usage = assetUsage(asset)
  return usage.startsWith('本页') ? 'used-current' : usage === '其他页已用' ? 'used-project' : 'unused'
}

function onSelectSlot(slotId: string) {
  selectedSlotId.value = slotId
}

function openCropEditor(slotId = selectedSlotId.value) {
  const slot = activePage.value.slots.find((item) => item.id === slotId)
  if (!slot?.src) return toast('请先给这个格子放入图片', true)
  selectedSlotId.value = slot.id
  showInspector.value = false
  if (!editor?.enterCrop(slot.id)) toast('裁切工具正在切换，请再试一次', true)
}

function finishCrop(commit = true) {
  editor?.finishCrop(commit)
}

function onImageChange(slotId: string, change: { cropX?: number; cropY?: number; zoom?: number }) {
  const slot = activePage.value.slots.find((item) => item.id === slotId)
  if (!slot) return
  Object.assign(slot, change)
  markDirty()
}

function clearSelected() {
  const slot = selectedSlot.value
  if (!slot) return
  slot.assetId = null
  slot.src = null
  slot.originalSrc = null
  slot.cropX = 0.5
  slot.cropY = 0.5
  slot.zoom = 1
  slot.imageLeft = undefined
  slot.imageTop = undefined
  slot.imageScale = undefined
  updateVisual()
}

async function resetCrop() {
  const slot = selectedSlot.value
  if (!slot?.src) return
  const reopen = cropMode.value
  if (reopen) editor?.finishCrop(false)
  slot.cropX = 0.5
  slot.cropY = 0.5
  slot.zoom = 1
  if (!reopen) return updateVisual()
  markDirty()
  await nextTick()
  await editor?.render(activePage.value, slot.id)
  editor?.enterCrop(slot.id)
}

function switchPage(pageId: string) {
  project.value.activePageId = pageId
  selectedSlotId.value = activePage.value.slots[0].id
  queueRender()
  showSettings.value = false
}

function addPage() {
  const page = createPage(project.value.pages.length + 1, {
    columns: activePage.value.columns,
    rows: activePage.value.rows,
    style: activePage.value.style,
    tone: activePage.value.tone,
  })
  project.value.pages.push(page)
  project.value.activePageId = page.id
  selectedSlotId.value = page.slots[0].id
  updateVisual()
}

function applyGrid(columns: number, rows: number) {
  const page = activePage.value
  const count = columns * rows
  page.columns = columns
  page.rows = rows
  page.slots = Array.from({ length: count }, (_, index) => page.slots[index] || createSlot(index))
  selectedSlotId.value = page.slots[0].id
  updateVisual()
}

function applyStyle(style: PosterStyle) {
  project.value.pages.forEach((page) => { page.style = { ...style } })
  updateVisual()
  toast('已将风格应用到全部图片页')
}

function applyStyleToAllPages() {
  const style = { ...activePage.value.style }
  const tone = activePage.value.tone
  project.value.pages.forEach((page) => {
    page.style = { ...style }
    page.tone = tone
  })
  updateVisual()
}

async function downloadPoster() {
  if (!placedCount.value) return toast('请先放入至少一张图片', true)
  if (!editor || exporting.value) return
  exporting.value = true
  try {
    editor.finishCrop(true)
    const blob = await renderPage(project.value, activePage.value)
    const dataUrl = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = dataUrl
    anchor.download = `${activePage.value.name.replace(/[\\/:*?"<>|]/g, '_')}_1080x1620.png`
    anchor.click()
    setTimeout(() => URL.revokeObjectURL(dataUrl), 1000)
    toast('已由原图渲染器导出1080×1620高清PNG')
  } catch (error) {
    toast(error instanceof Error ? error.message : '图片导出失败', true)
  } finally {
    exporting.value = false
  }
}

async function openProjectLibrary() {
  showProjects.value = true
  draftLoading.value = true
  try {
    draftItems.value = await listDrafts()
  } catch (error) {
    toast(error instanceof Error ? error.message : '项目库读取失败', true)
  } finally {
    draftLoading.value = false
  }
}

async function openDraft(id: number) {
  try {
    clearTimeout(saveTimer)
    project.value = await loadDraft(id)
    selectedSlotId.value = activePage.value.slots[0].id
    dirty.value = false
    saveKind.value = 'saved'
    saveState.value = '✓ 已从后台恢复'
    showProjects.value = false
    await nextTick()
    resetHistory()
    queueRender()
    toast(`已打开“${project.value.projectName}”`)
  } catch (error) {
    toast(error instanceof Error ? error.message : '项目打开失败', true)
  }
}

async function removeDraft(id: number, name: string) {
  if (!window.confirm(`确定删除项目“${name}”吗？删除后无法恢复。`)) return
  try {
    await deleteDraft(id)
    if (project.value.id === id) {
      project.value = createProject()
      selectedSlotId.value = activePage.value.slots[0].id
      dirty.value = false
      saveState.value = '当前为新项目'
      queueRender()
      resetHistory()
    }
    draftItems.value = await listDrafts()
    toast(`已删除项目“${name}”`)
  } catch (error) {
    toast(error instanceof Error ? error.message : '项目删除失败', true)
  }
}

function newProject() {
  clearTimeout(saveTimer)
  project.value = createProject()
  selectedSlotId.value = activePage.value.slots[0].id
  dirty.value = false
  saveState.value = '尚未修改'
  showProjects.value = false
  resetHistory()
  queueRender()
}

onMounted(() => {
  if (!canvasElement.value) return
  editor = new PosterCanvas(canvasElement.value, {
    onSelectSlot,
    onImageChange,
    onCropModeChange: (active) => { cropMode.value = active },
  })
  queueRender()
  if (canvasHost.value) {
    resizeObserver = new ResizeObserver(([entry]) => editor?.fit(entry.contentRect.width - 32))
    resizeObserver.observe(canvasHost.value)
  }
})

onBeforeUnmount(() => {
  clearTimeout(saveTimer)
  clearTimeout(toastTimer)
  clearTimeout(historyTimer)
  cancelAnimationFrame(renderFrame)
  resizeObserver?.disconnect()
  editor?.dispose()
})
</script>

<template>
  <div class="app-shell" :class="{ 'crop-mode': cropMode }">
    <header class="topbar">
      <div class="brand"><span class="brand-icon"><i /><i /><i /><i /></span><div><strong>方格志 <em>V2</em></strong><small>离线海报画布</small></div></div>
      <div class="top-actions">
        <span class="save-state" :class="saveKind">{{ saveState }}</span>
        <button class="button subtle history-button" :disabled="!canUndo" title="撤销" @click="undo">↶</button>
        <button class="button subtle history-button" :disabled="!canRedo" title="重做" @click="redo">↷</button>
        <button class="button subtle" @click="openProjectLibrary">项目库</button>
        <button class="button" :disabled="saving" @click="persist(false)">{{ saving ? '保存中…' : '保存' }}</button>
        <button class="button primary" :disabled="exporting" @click="downloadPoster">{{ exporting ? '生成中…' : '导出图片' }}</button>
      </div>
    </header>

    <main class="workspace">
      <aside class="settings-panel" :class="{ open: showSettings }">
        <div class="mobile-panel-head"><strong>项目与模板</strong><button class="icon-button" @click="showSettings = false">×</button></div>
        <section class="panel-section">
          <div class="section-heading"><b>项目信息</b><span>整套保存</span></div>
          <label>项目名称<input v-model="project.projectName" maxlength="50" @input="markDirty"></label>
          <label>项目说明<textarea v-model="project.description" maxlength="300" rows="3" @input="markDirty" /></label>
        </section>
        <section class="panel-section">
          <div class="section-heading"><b>图片页</b><button class="mini-button" @click="addPage">＋ 新建</button></div>
          <div class="page-tabs settings-tabs">
            <button v-for="(page, index) in project.pages" :key="page.id" :class="{ active: page.id === project.activePageId }" @click="switchPage(page.id)"><i>{{ index + 1 }}</i><span>{{ page.name }}</span></button>
          </div>
          <label>当前图片名称<input v-model="activePage.name" maxlength="50" @input="markDirty"></label>
          <label>图片描述<textarea v-model="activePage.description" maxlength="300" rows="2" @input="markDirty" /></label>
        </section>
        <section class="panel-section">
          <div class="section-heading"><b>海报标题</b><span>画布对象</span></div>
          <label>一级标题<input v-model="activePage.title" maxlength="80" @input="updateVisual"></label>
          <label>二级标题（可为空）<input v-model="activePage.subtitle" maxlength="100" placeholder="例如：12个50g" @input="updateVisual"></label>
        </section>
        <section class="panel-section">
          <div class="section-heading"><b>框架</b><span>固定2:3导出</span></div>
          <div class="layout-presets">
            <button v-for="layout in [[2,3],[3,3],[3,4],[4,3],[5,5]]" :key="layout.join('x')" :class="{ active: activePage.columns === layout[0] && activePage.rows === layout[1] }" @click="applyGrid(layout[0], layout[1])">{{ layout[0] }} × {{ layout[1] }}</button>
          </div>
        </section>
        <section class="panel-section">
          <div class="section-heading"><b>整套风格</b><span>默认应用全部图片页</span></div>
          <div class="style-presets">
            <button v-for="([id, style]) in styleEntries" :key="id" :class="{ active: activePage.style.accent === style.accent }" @click="applyStyle(style)"><span :style="{ background: style.background }"><i :style="{ background: style.accent }" /><i :style="{ background: style.panel }" /></span>{{ { amber: '暖橙教程', red: '小红书红', cream: '奶油杂志', ink: '深色质感' }[id] }}</button>
          </div>
          <label>全项目图片统一色调<select v-model="activePage.tone" @change="applyStyleToAllPages"><option value="original">自然原色</option><option value="warm">暖色统一</option><option value="cool">清冷统一</option><option value="bright">明亮清透</option><option value="film">柔和胶片</option></select></label>
          <button class="advanced-toggle" @click="showAdvancedStyle = !showAdvancedStyle">{{ showAdvancedStyle ? '收起高级样式' : '高级样式（颜色、圆角、间距）' }}</button>
          <div v-if="showAdvancedStyle" class="manual-style">
            <b>手动设计当前风格</b>
            <div class="color-controls">
              <label>画布背景<input v-model="activePage.style.background" type="color" @input="applyStyleToAllPages"></label>
              <label>主色/边框<input v-model="activePage.style.accent" type="color" @input="applyStyleToAllPages"></label>
              <label>备注底色<input v-model="activePage.style.panel" type="color" @input="applyStyleToAllPages"></label>
              <label>备注文字<input v-model="activePage.style.text" type="color" @input="applyStyleToAllPages"></label>
              <label>标题文字<input v-model="activePage.style.titleFill" type="color" @input="applyStyleToAllPages"></label>
              <label>标题描边<input v-model="activePage.style.titleStroke" type="color" @input="applyStyleToAllPages"></label>
            </div>
            <div class="style-ranges">
              <label>圆角 <output>{{ activePage.style.radius }}</output><input v-model.number="activePage.style.radius" type="range" min="0" max="48" step="1" @input="applyStyleToAllPages"></label>
              <label>格子间距 <output>{{ activePage.style.gap }}</output><input v-model.number="activePage.style.gap" type="range" min="0" max="30" step="1" @input="applyStyleToAllPages"></label>
            </div>
            <button class="button apply-all" @click="applyStyleToAllPages">确认应用到全部图片页</button>
          </div>
        </section>
      </aside>

      <section class="editor-column">
        <div class="page-tabs main-tabs">
          <button v-for="(page, index) in project.pages" :key="page.id" :class="{ active: page.id === project.activePageId }" @click="switchPage(page.id)"><i>{{ index + 1 }}</i><span>{{ page.name }}</span></button>
          <button class="add-tab" @click="addPage">＋</button>
        </div>

        <section class="asset-shelf">
          <div class="shelf-heading"><div><b>项目素材</b><span>{{ project.assets.length }}张 · 跨图片页标记使用状态</span></div><label class="button small"><input ref="fileInput" type="file" accept="image/*" multiple hidden @change="importFiles(($event.target as HTMLInputElement).files)">＋ 上传图片</label></div>
          <div v-if="project.assets.length" class="asset-strip">
            <button v-for="asset in project.assets" :key="asset.id" class="asset-card" :class="assetClass(asset)" @click="useAsset(asset)"><span class="asset-image"><img :src="asset.src" :alt="asset.name"><em>{{ assetUsage(asset) }}</em></span><small>{{ asset.name }}</small></button>
          </div>
          <button v-else class="asset-empty" @click="fileInput?.click()"><b>＋ 添加制作素材</b><span>一次可以上传任意数量，不受框架格子数限制</span></button>
          <p v-if="importing || importProgress" class="import-progress">{{ importing ? importProgress : importProgress }}</p>
        </section>

        <div class="stage-heading"><div><b>{{ activePage.name }}</b><span>{{ cropMode ? '拖动图片定位；拖动四角缩放图片' : '单击选择格子，双击图片直接裁切' }}</span></div><div class="stage-actions"><button class="mini-button" :disabled="!selectedSlot?.src || cropMode" @click="openCropEditor()">✂ 裁切图片</button><em>{{ placedCount }} / {{ activePage.slots.length }} 已放置</em></div></div>
        <div ref="canvasHost" class="canvas-host"><canvas ref="canvasElement" /></div>
        <div v-if="cropMode" class="crop-actionbar"><button class="button" @click="finishCrop(false)">取消</button><button class="button" @click="resetCrop">恢复居中</button><button class="button primary" @click="finishCrop(true)">完成裁切</button></div>
      </section>

      <aside class="inspector-panel" :class="{ open: showInspector }">
        <div class="mobile-panel-head"><strong>当前格子</strong><button class="icon-button" @click="showInspector = false">×</button></div>
        <section class="panel-section">
          <div class="section-heading"><b>第 {{ activePage.slots.indexOf(selectedSlot) + 1 }} 格</b><span>{{ selectedSlot?.src ? '已放置图片' : '等待图片' }}</span></div>
          <div class="selected-preview" :class="{ empty: !selectedSlot?.src }"><img v-if="selectedSlot?.src" :src="selectedSlot.src" alt="当前格预览"><span v-else>点击素材即可放入</span></div>
          <div v-if="selectedSlot?.src" class="crop-sliders">
            <button class="button crop-open" @click="openCropEditor()">✂ 在画布中直接裁切</button>
          </div>
          <label>步骤说明<textarea v-model="selectedSlot.note" maxlength="240" rows="5" placeholder="可输入多行，导出时自动换行" @input="updateVisual" /></label>
          <div class="inspector-actions"><button class="button" :disabled="!selectedSlot?.src" @click="resetCrop">恢复居中</button><button class="button danger" :disabled="!selectedSlot?.src" @click="clearSelected">清空格子</button></div>
        </section>
        <section class="help-card"><b>画布操作</b><p>先点格子，再点素材。双击图片进入裁切：拖动图片调整位置，拖动四角缩放；点“完成裁切”后自动保存。</p></section>
      </aside>
    </main>

    <nav v-if="!cropMode" class="mobile-bar">
      <button :disabled="!canUndo" @click="undo"><i>↶</i><span>撤销</span></button>
      <button @click="showSettings = true"><i>☰</i><span>设置</span></button>
      <button @click="fileInput?.click()"><i>＋</i><span>素材</span></button>
      <button @click="showInspector = true"><i>✎</i><span>格子</span></button>
      <button class="export" @click="downloadPoster"><i>↓</i><span>导出</span></button>
    </nav>
    <button v-if="showSettings || showInspector" class="mobile-backdrop" @click="showSettings = false; showInspector = false" />

    <div v-if="showProjects" class="modal" @click.self="showProjects = false">
      <div class="modal-card">
        <div class="modal-heading"><div><b>后台项目库</b><span>项目和素材保存在本地服务器</span></div><button class="icon-button" @click="showProjects = false">×</button></div>
        <button class="new-project" @click="newProject">＋ 创建空白项目</button>
        <div v-if="draftLoading" class="modal-empty">正在读取…</div>
        <div v-else-if="!draftItems.length" class="modal-empty">还没有保存过的项目</div>
        <div v-else class="draft-list">
          <article v-for="item in draftItems" :key="item.id"><div><b>{{ item.project_name }}</b><span>{{ item.page_count }}张图片 · {{ item.asset_count || 0 }}张素材 · {{ new Date(item.updated_at).toLocaleString() }}</span></div><button class="button small" @click="openDraft(item.id)">打开</button><button class="button small danger" @click="removeDraft(item.id, item.project_name)">删除</button></article>
        </div>
      </div>
    </div>
    <div v-if="toastText" class="toast" :class="{ error: toastError }">{{ toastText }}</div>
  </div>
</template>
