import { describe, expect, it } from 'vitest'
import sharp from 'sharp'
import { renderPoster } from '../render-server.mjs'

const style = {
  background: '#fff8e8', accent: '#f3a51f', panel: '#fff3d4', text: '#171715',
  titleFill: '#ffffff', titleStroke: '#171715', radius: 22, gap: 10,
}

describe('Sharp poster renderer', () => {
  it('always emits a 1080x1620 PNG', async () => {
    const png = await renderPoster({
      width: 1080, height: 1620, title: '离线导出', subtitle: '', rows: 1, columns: 1,
      tone: 'original', style,
      slots: [{ id: 'slot-1', src: null, originalSrc: null, note: '步骤说明', cropX: 0.5, cropY: 0.5, zoom: 1 }],
    })
    const metadata = await sharp(png).metadata()
    expect(metadata.format).toBe('png')
    expect(metadata.width).toBe(1080)
    expect(metadata.height).toBe(1620)
  })
})
