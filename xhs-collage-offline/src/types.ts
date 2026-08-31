export interface Asset {
  id: string
  name: string
  src: string
  originalSrc?: string
  mimeType?: string
  width?: number
  height?: number
}

export interface PosterSlot {
  id: string
  assetId: string | null
  src: string | null
  originalSrc?: string | null
  note: string
  cropX?: number
  cropY?: number
  zoom?: number
  imageLeft?: number
  imageTop?: number
  imageScale?: number
}

export interface PosterStyle {
  background: string
  accent: string
  panel: string
  text: string
  titleFill: string
  titleStroke: string
  radius: number
  gap: number
}

export interface PosterPage {
  id: string
  name: string
  description: string
  width: 1080
  height: 1620
  title: string
  subtitle: string
  rows: number
  columns: number
  tone: 'original' | 'warm' | 'cool' | 'bright' | 'film'
  slots: PosterSlot[]
  style: PosterStyle
}

export interface Project {
  id: number | null
  projectName: string
  description: string
  activePageId: string
  assets: Asset[]
  pages: PosterPage[]
}

export interface SlotLayout {
  x: number
  y: number
  width: number
  height: number
  imageHeight: number
  captionHeight: number
}

export interface TemplateLayout {
  width: number
  height: number
  header: { x: number; y: number; width: number; height: number }
  slots: SlotLayout[]
}
