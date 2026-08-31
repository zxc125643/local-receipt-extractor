import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

const ROOT = path.dirname(fileURLToPath(import.meta.url))
const DATA_DIR = path.resolve(process.env.XHS_DATA_DIR || ROOT)
const PORT = Number(process.env.XHS_RENDER_PORT || 8767)
const MAX_BODY = 6 * 1024 * 1024

const clamp = (value, min, max) => Math.max(min, Math.min(max, Number(value) || 0))
const esc = (value = '') => String(value).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' })[char])

function layout(page) {
  const outer = 12
  const headerHeight = 132
  const gap = clamp(page.style?.gap, 0, 30)
  const rows = clamp(page.rows, 1, 8)
  const columns = clamp(page.columns, 1, 8)
  const contentTop = outer + headerHeight + gap
  const cellWidth = (1080 - outer * 2 - gap * (columns - 1)) / columns
  const cellHeight = (1620 - contentTop - outer - gap * (rows - 1)) / rows
  const captionHeight = Math.max(76, Math.min(112, cellHeight * 0.2))
  return {
    header: { x: outer, y: outer, width: 1056, height: headerHeight },
    slots: page.slots.map((_, index) => ({
      x: outer + (index % columns) * (cellWidth + gap),
      y: contentTop + Math.floor(index / columns) * (cellHeight + gap),
      width: cellWidth,
      height: cellHeight,
      imageHeight: cellHeight - captionHeight,
      captionHeight,
    })),
  }
}

function resolveAsset(source) {
  if (!source || typeof source !== 'string') return null
  let filename
  try { filename = path.basename(decodeURIComponent(new URL(source, 'http://offline.local').pathname)) } catch { return null }
  if (!filename || filename === '.' || filename === '..') return null
  const candidates = [path.join(DATA_DIR, 'assets', filename), path.join(ROOT, 'assets', filename)]
  return candidates.find((candidate) => fs.existsSync(candidate) && fs.statSync(candidate).isFile()) || null
}

function roundedMask(width, height, radius) {
  return Buffer.from(`<svg width="${width}" height="${height}" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" rx="${Math.min(radius, width / 2, height / 2)}" fill="white"/></svg>`)
}

async function renderPhoto(file, slot, box, tone, radius) {
  const oriented = await sharp(file).rotate().toBuffer({ resolveWithObject: true })
  const width = oriented.info.width
  const height = oriented.info.height
  const aspect = box.width / box.imageHeight
  const baseWidth = Math.min(width, height * aspect)
  const baseHeight = Math.min(height, width / aspect)
  const zoom = clamp(slot.zoom || 1, 1, 3)
  const cropWidth = Math.max(1, Math.round(baseWidth / zoom))
  const cropHeight = Math.max(1, Math.round(baseHeight / zoom))
  const left = Math.round((width - cropWidth) * clamp(slot.cropX ?? 0.5, 0, 1))
  const top = Math.round((height - cropHeight) * clamp(slot.cropY ?? 0.5, 0, 1))
  let pipeline = sharp(oriented.data)
    .extract({ left, top, width: cropWidth, height: cropHeight })
    .resize(Math.round(box.width), Math.round(box.imageHeight), { fit: 'fill', kernel: sharp.kernel.lanczos3 })
  if (tone === 'warm') pipeline = pipeline.modulate({ brightness: 1.035, saturation: 0.96, hue: 4 })
  if (tone === 'cool') pipeline = pipeline.modulate({ brightness: 1.025, saturation: 0.93, hue: 356 })
  if (tone === 'bright') pipeline = pipeline.modulate({ brightness: 1.07, saturation: 0.97 })
  if (tone === 'film') pipeline = pipeline.modulate({ brightness: 1.025, saturation: 0.82 }).gamma(1.05)
  const photo = await pipeline.png().toBuffer()
  return sharp(photo).composite([{ input: roundedMask(Math.round(box.width), Math.round(box.imageHeight), radius), blend: 'dest-in' }]).png().toBuffer()
}

function textLines(text, maxChars, maxLines = 2) {
  const source = String(text || '').trim()
  if (!source) return []
  const lines = []
  let current = ''
  for (const char of source) {
    if (char === '\n' || current.length >= maxChars) {
      if (current) lines.push(current)
      current = char === '\n' ? '' : char
      if (lines.length >= maxLines) break
    } else current += char
  }
  if (current && lines.length < maxLines) lines.push(current)
  if (lines.join('').length < source.replace(/\n/g, '').length && lines.length) lines[lines.length - 1] = `${lines[lines.length - 1].slice(0, -1)}…`
  return lines
}

function overlaySvg(page, boxes) {
  const style = page.style || {}
  const radius = clamp(style.radius, 0, 48)
  const titleSize = page.columns > 3 ? 48 : 62
  const header = boxes.header
  const nodes = [
    `<defs><linearGradient id="header" x1="0" x2="1"><stop offset="0" stop-color="${esc(style.accent)}"/><stop offset=".52" stop-color="#ffd873"/><stop offset="1" stop-color="${esc(style.accent)}"/></linearGradient></defs>`,
    `<rect x="${header.x}" y="${header.y}" width="${header.width}" height="${header.height}" rx="${radius}" fill="url(#header)" stroke="${esc(style.accent)}" stroke-width="2"/>`,
    `<text x="540" y="${header.y + (page.subtitle ? 75 : 88)}" text-anchor="middle" font-family="Noto Sans CJK SC,Microsoft YaHei,sans-serif" font-size="${titleSize}" font-weight="900" fill="${esc(style.titleFill)}" stroke="${esc(style.titleStroke)}" stroke-width="5" paint-order="stroke">${esc(page.title || '输入教程标题')}</text>`,
  ]
  if (page.subtitle) nodes.push(`<text x="540" y="${header.y + 116}" text-anchor="middle" font-family="Noto Sans CJK SC,Microsoft YaHei,sans-serif" font-size="25" font-weight="700" fill="${esc(style.titleFill)}" stroke="${esc(style.titleStroke)}" stroke-width="2" paint-order="stroke">${esc(page.subtitle)}</text>`)
  boxes.slots.forEach((box, index) => {
    const slot = page.slots[index]
    const captionY = box.y + box.imageHeight
    const badge = Math.min(54, box.captionHeight - 24)
    const fontSize = Math.max(17, Math.min(32, box.width * 0.065))
    const textX = box.x + 18 + badge + 14
    const maxChars = Math.max(4, Math.floor((box.width - badge - 54) / (fontSize * 0.95)))
    nodes.push(`<rect x="${box.x}" y="${captionY}" width="${box.width}" height="${box.captionHeight}" rx="${radius}" fill="${esc(style.panel)}" stroke="${esc(style.accent)}" stroke-width="2"/>`)
    nodes.push(`<circle cx="${box.x + 18 + badge / 2}" cy="${captionY + box.captionHeight / 2}" r="${badge / 2}" fill="white" stroke="${esc(style.text)}" stroke-width="3"/>`)
    nodes.push(`<text x="${box.x + 18 + badge / 2}" y="${captionY + box.captionHeight / 2 + badge * 0.19}" text-anchor="middle" font-family="Arial,sans-serif" font-size="${badge * 0.53}" font-weight="900" fill="${esc(style.text)}">${index + 1}</text>`)
    const lines = textLines(slot.note || '填写步骤说明', maxChars, box.captionHeight > 94 ? 2 : 1)
    const startY = captionY + (box.captionHeight - lines.length * fontSize * 1.12) / 2 + fontSize * 0.85
    lines.forEach((line, lineIndex) => nodes.push(`<text x="${textX}" y="${startY + lineIndex * fontSize * 1.12}" font-family="Noto Sans CJK SC,Microsoft YaHei,sans-serif" font-size="${fontSize}" font-weight="800" fill="${esc(slot.note ? style.text : '#aaa39a')}">${esc(line)}</text>`))
    nodes.push(`<rect x="${box.x}" y="${box.y}" width="${box.width}" height="${box.height}" rx="${radius}" fill="none" stroke="${esc(style.accent)}" stroke-width="2"/>`)
  })
  return Buffer.from(`<svg width="1080" height="1620" xmlns="http://www.w3.org/2000/svg">${nodes.join('')}</svg>`)
}

export async function renderPoster(page) {
  if (!page || !Array.isArray(page.slots)) throw new Error('缺少有效图片页数据')
  const boxes = layout(page)
  const composites = []
  for (let index = 0; index < page.slots.length; index += 1) {
    const slot = page.slots[index]
    const box = boxes.slots[index]
    const file = resolveAsset(slot.originalSrc || slot.src)
    if (!file && (slot.originalSrc || slot.src)) throw new Error(`第 ${index + 1} 格原图不存在，请重新上传素材`)
    if (!file) continue
    const input = await renderPhoto(file, slot, box, page.tone, clamp(page.style?.radius, 0, 48))
    composites.push({ input, left: Math.round(box.x), top: Math.round(box.y) })
  }
  composites.push({ input: overlaySvg(page, boxes), left: 0, top: 0 })
  return sharp({ create: { width: 1080, height: 1620, channels: 4, background: page.style?.background || '#fff8e8' } }).composite(composites).png({ compressionLevel: 9, adaptiveFiltering: true }).toBuffer()
}

function sendJson(response, status, body) {
  response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' })
  response.end(JSON.stringify(body))
}

export function createRenderServer() {
  return http.createServer((request, response) => {
    if (request.method === 'GET' && request.url === '/health') return sendJson(response, 200, { ok: true })
    if (request.method !== 'POST' || request.url !== '/api/render') return sendJson(response, 404, { error: '接口不存在' })
    let size = 0
    const chunks = []
    request.on('data', (chunk) => {
      size += chunk.length
      if (size > MAX_BODY) request.destroy(new Error('请求数据过大'))
      else chunks.push(chunk)
    })
    request.on('end', async () => {
      try {
        const body = JSON.parse(Buffer.concat(chunks).toString('utf8'))
        const png = await renderPoster(body.page)
        response.writeHead(200, { 'Content-Type': 'image/png', 'Content-Length': png.length, 'Cache-Control': 'no-store' })
        response.end(png)
      } catch (error) {
        sendJson(response, 400, { error: error instanceof Error ? error.message : '图片生成失败' })
      }
    })
    request.on('error', (error) => sendJson(response, 400, { error: error.message }))
  })
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  createRenderServer().listen(PORT, '0.0.0.0', () => console.log(`Sharp render server: http://0.0.0.0:${PORT}`))
}
