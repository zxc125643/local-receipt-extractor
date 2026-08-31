import pica from 'pica'
import { uploadAsset } from './api'
import type { Asset } from '../types'

const PREVIEW_MAX_SIDE = 2048

async function makePreview(file: File): Promise<{ blob: Blob; width: number; height: number } | null> {
  let bitmap: ImageBitmap | undefined
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
    const longest = Math.max(bitmap.width, bitmap.height)
    if (longest <= PREVIEW_MAX_SIDE) return { blob: file, width: bitmap.width, height: bitmap.height }
    const ratio = PREVIEW_MAX_SIDE / longest
    const width = Math.max(1, Math.round(bitmap.width * ratio))
    const height = Math.max(1, Math.round(bitmap.height * ratio))
    const source = document.createElement('canvas')
    source.width = bitmap.width
    source.height = bitmap.height
    source.getContext('2d', { alpha: true })?.drawImage(bitmap, 0, 0)
    const target = document.createElement('canvas')
    target.width = width
    target.height = height
    await pica().resize(source, target, { quality: 3 })
    return { blob: await pica().toBlob(target, 'image/webp', 0.88), width, height }
  } catch {
    return null
  } finally {
    bitmap?.close()
  }
}

export async function processAndUploadImage(file: File): Promise<Asset> {
  const original = await uploadAsset(file, file.name)
  const preview = await makePreview(file)
  if (!preview || preview.blob === file) {
    return { ...original, originalSrc: original.src, width: preview?.width, height: preview?.height }
  }
  const previewName = `${file.name.replace(/\.[^.]+$/, '')}-preview.webp`
  const uploadedPreview = await uploadAsset(preview.blob, previewName)
  return {
    id: original.id,
    name: file.name,
    src: uploadedPreview.src,
    originalSrc: original.src,
    mimeType: file.type,
    width: preview.width,
    height: preview.height,
  }
}
