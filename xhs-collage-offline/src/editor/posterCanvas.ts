import { Canvas, Circle, FabricImage, FabricObject, FabricText, Gradient, Rect, Textbox, filters } from 'fabric'
import { getTemplateLayout } from './template'
import type { PosterPage, PosterSlot } from '../types'

type ObjectRole = 'slot' | 'image'
type TaggedObject = FabricObject & { data?: { role: ObjectRole; slotId: string } }

export interface PosterCanvasEvents {
  onSelectSlot: (slotId: string) => void
  onEditImage: (slotId: string) => void
  onImageChange: (slotId: string, change: Pick<PosterSlot, 'cropX' | 'cropY' | 'zoom'>) => void
}

export class PosterCanvas {
  private canvas: Canvas
  private page: PosterPage | null = null
  private renderVersion = 0

  constructor(element: HTMLCanvasElement, private events: PosterCanvasEvents) {
    this.canvas = new Canvas(element, {
      width: 1080,
      height: 1620,
      selection: false,
      preserveObjectStacking: true,
      backgroundColor: '#fff8e8',
    })
    this.canvas.on('mouse:down', ({ target }) => {
      const tagged = target as TaggedObject | undefined
      if (tagged?.data?.slotId) this.events.onSelectSlot(tagged.data.slotId)
    })
    this.canvas.on('mouse:dblclick', ({ target }) => {
      const tagged = target as TaggedObject | undefined
      if (tagged?.data?.role === 'image' && tagged.data.slotId) this.events.onEditImage(tagged.data.slotId)
    })
    this.canvas.on('selection:created', ({ selected }) => this.emitSelection(selected?.[0]))
    this.canvas.on('selection:updated', ({ selected }) => this.emitSelection(selected?.[0]))
    this.canvas.on('object:moving', ({ target }) => this.constrainImage(target))
    this.canvas.on('object:scaling', ({ target }) => this.constrainImage(target))
    this.canvas.on('object:modified', ({ target }) => this.emitImageChange(target))
  }

  private emitSelection(target?: FabricObject) {
    const tagged = target as TaggedObject | undefined
    if (tagged?.data?.slotId) this.events.onSelectSlot(tagged.data.slotId)
  }

  private emitImageChange(target?: FabricObject) {
    const tagged = target as TaggedObject | undefined
    if (tagged?.data?.role !== 'image' || !tagged.data.slotId || !this.page) return
    this.constrainImage(target)
    const index = this.page.slots.findIndex((slot) => slot.id === tagged.data?.slotId)
    if (index < 0) return
    const box = getTemplateLayout(this.page).slots[index]
    const width = (target?.width || 1) * (target?.scaleX || 1)
    const height = (target?.height || 1) * (target?.scaleY || 1)
    const coverScale = Math.max(box.width / (target?.width || 1), box.imageHeight / (target?.height || 1))
    this.events.onImageChange(tagged.data.slotId, {
      cropX: Math.max(0, Math.min(1, (box.x - (target?.left ?? box.x)) / Math.max(1, width - box.width))),
      cropY: Math.max(0, Math.min(1, (box.y - (target?.top ?? box.y)) / Math.max(1, height - box.imageHeight))),
      zoom: Math.max(1, (target?.scaleX || coverScale) / coverScale),
    })
  }

  private constrainImage(target?: FabricObject) {
    const tagged = target as TaggedObject | undefined
    if (tagged?.data?.role !== 'image' || !this.page) return
    const index = this.page.slots.findIndex((slot) => slot.id === tagged.data?.slotId)
    if (index < 0) return
    const box = getTemplateLayout(this.page).slots[index]
    const coverScale = Math.max(box.width / (target?.width || 1), box.imageHeight / (target?.height || 1))
    const scale = Math.max(coverScale, target?.scaleX || coverScale, target?.scaleY || coverScale)
    target?.set({ scaleX: scale, scaleY: scale })
    const width = (target?.width || 1) * scale
    const height = (target?.height || 1) * scale
    target?.set({
      left: Math.max(box.x + box.width - width, Math.min(box.x, target.left ?? box.x)),
      top: Math.max(box.y + box.imageHeight - height, Math.min(box.y, target.top ?? box.y)),
    })
  }

  async render(page: PosterPage, selectedSlotId?: string) {
    const version = ++this.renderVersion
    this.page = page
    this.canvas.discardActiveObject()
    this.canvas.clear()
    this.canvas.backgroundColor = page.style.background
    const layout = getTemplateLayout(page)
    const headerFill = new Gradient({
      type: 'linear',
      coords: { x1: 0, y1: 0, x2: layout.header.width, y2: 0 },
      colorStops: [
        { offset: 0, color: page.style.accent },
        { offset: 0.52, color: this.lighten(page.style.accent, 32) },
        { offset: 1, color: page.style.accent },
      ],
    })
    this.canvas.add(new Rect({
      ...layout.header,
      originX: 'left',
      originY: 'top',
      rx: page.style.radius,
      ry: page.style.radius,
      fill: headerFill,
      stroke: this.lighten(page.style.accent, -8),
      strokeWidth: 2,
      selectable: false,
      evented: false,
    }))
    this.canvas.add(new Textbox(page.title || '输入教程标题', {
      left: layout.header.x + 42,
      top: layout.header.y + (page.subtitle ? 20 : 32),
      originX: 'left',
      originY: 'top',
      width: layout.header.width - 84,
      fontFamily: 'Microsoft YaHei, PingFang SC, sans-serif',
      fontSize: page.columns > 3 ? 48 : 62,
      fontWeight: 900,
      textAlign: 'center',
      fill: page.style.titleFill,
      stroke: page.style.titleStroke,
      strokeWidth: 5,
      paintFirst: 'stroke',
      selectable: false,
      evented: false,
    }))
    if (page.subtitle) {
      this.canvas.add(new Textbox(page.subtitle, {
        left: layout.header.x + 60,
        top: layout.header.y + 91,
        originX: 'left',
        originY: 'top',
        width: layout.header.width - 120,
        fontFamily: 'Microsoft YaHei, PingFang SC, sans-serif',
        fontSize: 25,
        fontWeight: 700,
        textAlign: 'center',
        fill: page.style.titleFill,
        stroke: page.style.titleStroke,
        strokeWidth: 2,
        paintFirst: 'stroke',
        selectable: false,
        evented: false,
      }))
    }

    for (let index = 0; index < page.slots.length; index += 1) {
      const slot = page.slots[index]
      const box = layout.slots[index]
      this.addSlotBase(slot, box, page)
      if (slot.src) await this.addSlotImage(slot, box, page, version)
      this.addSlotCaption(slot, index, box, page)
    }
    if (version !== this.renderVersion) return
    if (selectedSlotId) {
      const image = this.canvas.getObjects().find((object) => (object as TaggedObject).data?.role === 'image' && (object as TaggedObject).data?.slotId === selectedSlotId)
      if (image) this.canvas.setActiveObject(image)
    }
    this.canvas.requestRenderAll()
  }

  private addSlotBase(slot: PosterSlot, box: ReturnType<typeof getTemplateLayout>['slots'][number], page: PosterPage) {
    const background = new Rect({
      left: box.x,
      top: box.y,
      originX: 'left',
      originY: 'top',
      width: box.width,
      height: box.imageHeight,
      rx: page.style.radius,
      ry: page.style.radius,
      fill: '#e8e4dc',
      stroke: page.style.accent,
      strokeWidth: 2,
      selectable: false,
      evented: true,
    }) as TaggedObject
    background.data = { role: 'slot', slotId: slot.id }
    this.canvas.add(background)
    if (!slot.src) {
      this.canvas.add(new FabricText('点击上方素材放入图片', {
        left: box.x + box.width / 2,
        top: box.y + box.imageHeight / 2,
        originX: 'center',
        originY: 'center',
        fontFamily: 'Microsoft YaHei, sans-serif',
        fontSize: Math.max(16, Math.min(25, box.width * 0.07)),
        fill: '#9c968c',
        selectable: false,
        evented: false,
      }))
    }
  }

  private async addSlotImage(slot: PosterSlot, box: ReturnType<typeof getTemplateLayout>['slots'][number], page: PosterPage, version: number) {
    try {
      const image = await FabricImage.fromURL(slot.src || '', { crossOrigin: 'anonymous' })
      if (version !== this.renderVersion) return
      image.filters = this.filtersForTone(page.tone)
      image.applyFilters()
      const naturalWidth = image.width || 1
      const naturalHeight = image.height || 1
      const coverScale = Math.max(box.width / naturalWidth, box.imageHeight / naturalHeight)
      const scale = coverScale * Math.max(1, slot.zoom || 1)
      const imageWidth = naturalWidth * scale
      const imageHeight = naturalHeight * scale
      image.set({
        left: box.x - Math.max(0, imageWidth - box.width) * Math.max(0, Math.min(1, slot.cropX ?? 0.5)),
        top: box.y - Math.max(0, imageHeight - box.imageHeight) * Math.max(0, Math.min(1, slot.cropY ?? 0.5)),
        originX: 'left',
        originY: 'top',
        scaleX: scale,
        scaleY: scale,
        lockRotation: true,
        cornerColor: page.style.accent,
        cornerStrokeColor: '#ffffff',
        borderColor: page.style.accent,
        cornerSize: 30,
        transparentCorners: false,
        clipPath: new Rect({
          left: box.x,
          top: box.y,
          originX: 'left',
          originY: 'top',
          width: box.width,
          height: box.imageHeight,
          rx: page.style.radius,
          ry: page.style.radius,
          absolutePositioned: true,
        }),
      })
      image.setControlsVisibility({ mt: false, mb: false, ml: false, mr: false, mtr: false })
      const tagged = image as TaggedObject
      tagged.data = { role: 'image', slotId: slot.id }
      this.canvas.add(image)
    } catch {
      this.canvas.add(new FabricText('图片读取失败', {
        left: box.x + box.width / 2,
        top: box.y + box.imageHeight / 2,
        originX: 'center',
        originY: 'center',
        fontSize: 22,
        fill: '#b33441',
        selectable: false,
        evented: false,
      }))
    }
  }

  private addSlotCaption(slot: PosterSlot, index: number, box: ReturnType<typeof getTemplateLayout>['slots'][number], page: PosterPage) {
    const captionTop = box.y + box.imageHeight
    this.canvas.add(new Rect({
      left: box.x,
      top: captionTop,
      originX: 'left',
      originY: 'top',
      width: box.width,
      height: box.captionHeight,
      rx: page.style.radius,
      ry: page.style.radius,
      fill: page.style.panel,
      stroke: page.style.accent,
      strokeWidth: 2,
      selectable: false,
      evented: false,
    }))
    const badgeSize = Math.min(54, box.captionHeight - 24)
    const badgeLeft = box.x + 18
    const badgeTop = captionTop + (box.captionHeight - badgeSize) / 2
    this.canvas.add(new Circle({
      left: badgeLeft,
      top: badgeTop,
      originX: 'left',
      originY: 'top',
      radius: badgeSize / 2,
      fill: '#ffffff',
      stroke: page.style.text,
      strokeWidth: 3,
      selectable: false,
      evented: false,
    }))
    this.canvas.add(new FabricText(String(index + 1), {
      left: badgeLeft + badgeSize / 2,
      top: badgeTop + badgeSize / 2,
      originX: 'center',
      originY: 'center',
      fontFamily: 'Arial, sans-serif',
      fontSize: badgeSize * 0.53,
      fontWeight: 900,
      fill: page.style.text,
      selectable: false,
      evented: false,
    }))
    this.canvas.add(new Textbox(slot.note || '填写步骤说明', {
      left: badgeLeft + badgeSize + 14,
      top: captionTop + 17,
      originX: 'left',
      originY: 'top',
      width: box.width - badgeSize - 54,
      height: box.captionHeight - 28,
      fontFamily: 'Microsoft YaHei, PingFang SC, sans-serif',
      fontSize: Math.max(17, Math.min(32, box.width * 0.065)),
      fontWeight: 800,
      lineHeight: 1.1,
      fill: slot.note ? page.style.text : '#aaa39a',
      selectable: false,
      evented: false,
    }))
    this.canvas.add(new Rect({
      left: box.x,
      top: box.y,
      originX: 'left',
      originY: 'top',
      width: box.width,
      height: box.height,
      rx: page.style.radius,
      ry: page.style.radius,
      fill: 'transparent',
      stroke: page.style.accent,
      strokeWidth: 2,
      selectable: false,
      evented: false,
    }))
  }

  fit(maxWidth: number) {
    if (!this.page) return
    const width = Math.max(260, Math.min(maxWidth, this.page.width))
    this.canvas.setDimensions({ width, height: width * 1.5 }, { cssOnly: true })
  }

  async exportPng(page: PosterPage): Promise<string> {
    const selectedSlotId = (this.canvas.getActiveObject() as TaggedObject | undefined)?.data?.slotId
    const exportPage: PosterPage = {
      ...page,
      slots: page.slots.map((slot) => ({ ...slot, src: slot.originalSrc || slot.src })),
    }
    await this.render(exportPage)
    this.canvas.discardActiveObject()
    this.canvas.requestRenderAll()
    const result = this.canvas.toDataURL({ format: 'png', quality: 1, multiplier: 1 })
    await this.render(page, selectedSlotId)
    return result
  }

  dispose() {
    this.renderVersion += 1
    this.canvas.dispose()
  }

  private lighten(hex: string, amount: number): string {
    const normalized = hex.replace('#', '')
    if (!/^[0-9a-f]{6}$/i.test(normalized)) return hex
    const value = Number.parseInt(normalized, 16)
    const channel = (shift: number) => Math.max(0, Math.min(255, ((value >> shift) & 255) + amount))
    return `#${[channel(16), channel(8), channel(0)].map((part) => part.toString(16).padStart(2, '0')).join('')}`
  }

  private filtersForTone(tone: PosterPage['tone']) {
    if (tone === 'warm') return [new filters.Brightness({ brightness: 0.025 }), new filters.Saturation({ saturation: -0.05 }), new filters.BlendColor({ color: '#f2a65a', mode: 'tint', alpha: 0.07 })]
    if (tone === 'cool') return [new filters.Brightness({ brightness: 0.025 }), new filters.Saturation({ saturation: -0.08 }), new filters.BlendColor({ color: '#8eb9e8', mode: 'tint', alpha: 0.06 })]
    if (tone === 'bright') return [new filters.Brightness({ brightness: 0.065 }), new filters.Contrast({ contrast: 0.025 }), new filters.Saturation({ saturation: -0.03 })]
    if (tone === 'film') return [new filters.Brightness({ brightness: 0.02 }), new filters.Contrast({ contrast: -0.035 }), new filters.Saturation({ saturation: -0.18 }), new filters.BlendColor({ color: '#d2ad78', mode: 'tint', alpha: 0.045 })]
    return []
  }
}
