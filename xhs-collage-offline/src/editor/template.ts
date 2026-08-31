import type { Asset, PosterPage, PosterSlot, PosterStyle, Project, TemplateLayout } from '../types'

export const STYLE_PRESETS: Record<string, PosterStyle> = {
  amber: { background: '#fff8e8', accent: '#f3a51f', panel: '#fff3d4', text: '#171715', titleFill: '#ffffff', titleStroke: '#171715', radius: 22, gap: 10 },
  red: { background: '#fff4f2', accent: '#ef4056', panel: '#fffaf9', text: '#25191a', titleFill: '#ffffff', titleStroke: '#3a1118', radius: 20, gap: 10 },
  cream: { background: '#f5efe3', accent: '#9b7048', panel: '#fffdf8', text: '#342a22', titleFill: '#fffdf8', titleStroke: '#342a22', radius: 16, gap: 12 },
  ink: { background: '#20201e', accent: '#e8c66a', panel: '#302f2b', text: '#ffffff', titleFill: '#ffffff', titleStroke: '#111111', radius: 14, gap: 8 },
}

function makeId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function createSlot(index: number, source: Partial<PosterSlot> = {}): PosterSlot {
  return {
    id: source.id || `slot-${index + 1}`,
    assetId: source.assetId || null,
    src: source.src || null,
    originalSrc: source.originalSrc || source.src || null,
    note: source.note || '',
    cropX: source.cropX ?? 0.5,
    cropY: source.cropY ?? 0.5,
    zoom: source.zoom ?? 1,
    imageLeft: source.imageLeft,
    imageTop: source.imageTop,
    imageScale: source.imageScale,
  }
}

export function createPage(index = 1, source: Partial<PosterPage> = {}): PosterPage {
  const rows = Math.max(1, Math.min(8, Number(source.rows) || 3))
  const columns = Math.max(1, Math.min(8, Number(source.columns) || 2))
  const count = rows * columns
  const sourceSlots = Array.isArray(source.slots) ? source.slots : []
  return {
    id: source.id || makeId('page'),
    name: source.name || `图片 ${index}`,
    description: source.description || '',
    width: 1080,
    height: 1620,
    title: source.title || '输入教程标题',
    subtitle: source.subtitle || '',
    rows,
    columns,
    tone: source.tone || 'original',
    slots: Array.from({ length: count }, (_, slotIndex) => createSlot(slotIndex, sourceSlots[slotIndex])),
    style: { ...STYLE_PRESETS.amber, ...(source.style || {}) },
  }
}

export function getTemplateLayout(page: PosterPage): TemplateLayout {
  const outer = 12
  const headerHeight = 132
  const contentTop = outer + headerHeight + page.style.gap
  const availableWidth = page.width - outer * 2 - page.style.gap * (page.columns - 1)
  const cellWidth = availableWidth / page.columns
  const availableHeight = page.height - contentTop - outer - page.style.gap * (page.rows - 1)
  const cellHeight = availableHeight / page.rows
  const captionHeight = Math.max(76, Math.min(112, cellHeight * 0.2))
  return {
    width: page.width,
    height: page.height,
    header: { x: outer, y: outer, width: page.width - outer * 2, height: headerHeight },
    slots: page.slots.map((_, index) => {
      const column = index % page.columns
      const row = Math.floor(index / page.columns)
      return {
        x: outer + column * (cellWidth + page.style.gap),
        y: contentTop + row * (cellHeight + page.style.gap),
        width: cellWidth,
        height: cellHeight,
        imageHeight: cellHeight - captionHeight,
        captionHeight,
      }
    }),
  }
}

type LegacyRecord = Record<string, unknown>

function legacyAssets(value: unknown): Asset[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item, index) => {
    const asset = (item || {}) as LegacyRecord
    const src = typeof asset.src === 'string' ? asset.src : ''
    if (!src) return []
    return [{ id: String(asset.id || `asset-${index + 1}`), name: String(asset.name || `素材 ${index + 1}`), src, originalSrc: typeof asset.originalSrc === 'string' ? asset.originalSrc : src }]
  })
}

export function normalizeLegacyDraft(raw: LegacyRecord): Project {
  const assets = legacyAssets(raw.assets)
  const rawPages = Array.isArray(raw.pages) && raw.pages.length ? raw.pages : [raw]
  const pages = rawPages.map((value, pageIndex) => {
    const page = (value || {}) as LegacyRecord
    const storedSlots = Array.isArray(page.slots)
      ? page.slots
      : (Array.isArray(page.cells) ? page.cells : [])
    const slots = storedSlots.map((value, slotIndex) => {
      const cell = (value || {}) as LegacyRecord
      return createSlot(slotIndex, {
        id: typeof cell.id === 'string' ? cell.id : undefined,
        assetId: typeof cell.assetId === 'string' ? cell.assetId : null,
        src: typeof cell.src === 'string' ? cell.src : null,
        originalSrc: typeof cell.originalSrc === 'string' ? cell.originalSrc : (typeof cell.src === 'string' ? cell.src : null),
        note: typeof cell.note === 'string' ? cell.note : '',
        cropX: typeof cell.cropX === 'number' ? cell.cropX : 0.5 + Number(cell.offsetX || cell.offset_x || 0) / 200,
        cropY: typeof cell.cropY === 'number' ? cell.cropY : 0.5 + Number(cell.offsetY || cell.offset_y || 0) / 200,
        zoom: typeof cell.zoom === 'number' ? (Number(cell.zoom) > 10 ? Number(cell.zoom) / 100 : Number(cell.zoom)) : 1,
        imageScale: typeof cell.imageScale === 'number' ? cell.imageScale : undefined,
        imageLeft: typeof cell.imageLeft === 'number' ? cell.imageLeft : undefined,
        imageTop: typeof cell.imageTop === 'number' ? cell.imageTop : undefined,
      })
    })
    return createPage(pageIndex + 1, {
      id: typeof page.id === 'string' ? page.id : undefined,
      name: typeof page.name === 'string' ? page.name : undefined,
      description: typeof page.description === 'string' ? page.description : undefined,
      title: String(page.title || page.frameTitle || page.frame_title || ''),
      subtitle: String(page.subtitle || page.frameSubtitle || page.frame_subtitle || ''),
      rows: Number(page.rows) || Math.max(3, Math.ceil(slots.length / 2)),
      columns: Number(page.columns || page.cols) || 2,
      tone: ['warm', 'cool', 'bright', 'film'].includes(String(page.tone)) ? page.tone as PosterPage['tone'] : 'original',
      slots,
      style: (page.style || undefined) as PosterStyle | undefined,
    })
  })
  const activePageId = typeof raw.active_page_id === 'string' && pages.some((page) => page.id === raw.active_page_id)
    ? raw.active_page_id
    : pages[0].id
  const assetBySource = new Map<string, Asset>()
  assets.forEach((asset) => {
    assetBySource.set(asset.src, asset)
    if (asset.originalSrc) assetBySource.set(asset.originalSrc, asset)
  })
  pages.forEach((page) => page.slots.forEach((slot) => {
    if (!slot.src) return
    let asset = assetBySource.get(slot.src)
    if (!asset) {
      asset = {
        id: makeId('asset'),
        name: `旧素材 ${assets.length + 1}`,
        src: slot.src,
        originalSrc: slot.originalSrc || slot.src,
      }
      assets.push(asset)
      assetBySource.set(asset.src, asset)
      if (asset.originalSrc) assetBySource.set(asset.originalSrc, asset)
    }
    slot.assetId ||= asset.id
    slot.originalSrc ||= asset.originalSrc || asset.src
  }))
  return {
    id: typeof raw.id === 'number' ? raw.id : null,
    projectName: String(raw.project_name || raw.name || '未命名项目'),
    description: String(raw.project_description || raw.description || ''),
    activePageId,
    assets,
    pages,
  }
}

export function createProject(): Project {
  const page = createPage(1)
  return { id: null, projectName: '未命名项目', description: '', activePageId: page.id, assets: [], pages: [page] }
}
