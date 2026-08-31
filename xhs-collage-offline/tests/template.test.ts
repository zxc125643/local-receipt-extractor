import { describe, expect, it } from 'vitest'
import { createPage, getTemplateLayout, normalizeLegacyDraft } from '../src/editor/template'

describe('tutorial poster template', () => {
  it('creates one 2:3 poster with six editable slots', () => {
    const page = createPage(1)
    expect(page.width).toBe(1080)
    expect(page.height).toBe(1620)
    expect(page.slots).toHaveLength(6)
    expect(getTemplateLayout(page).slots).toHaveLength(6)
  })

  it('preserves legacy page titles, notes and assets', () => {
    const project = normalizeLegacyDraft({
      id: 7,
      project_name: '月饼教程',
      assets: [{ id: 'a1', src: 'data:image/jpeg;base64,AA==', name: '步骤1.jpg' }],
      pages: [{ name: '图片 1', frameTitle: '广式月饼', frameSubtitle: '12个50g', cells: [{ assetId: 'a1', src: 'data:image/jpeg;base64,AA==', note: '混合材料' }] }],
    })
    expect(project.id).toBe(7)
    expect(project.pages[0].title).toBe('广式月饼')
    expect(project.pages[0].subtitle).toBe('12个50g')
    expect(project.pages[0].slots[0].note).toBe('混合材料')
    expect(project.assets[0].id).toBe('a1')
  })

  it('rebuilds the material library when an old draft only stored images in cells', () => {
    const project = normalizeLegacyDraft({
      project_name: '旧项目',
      pages: [{ cells: [{ src: '/assets/step-1.jpg', note: '揉成团' }, { src: '/assets/step-1.jpg' }] }],
    })

    expect(project.assets).toHaveLength(1)
    expect(project.assets[0].src).toBe('/assets/step-1.jpg')
    expect(project.pages[0].slots[0].assetId).toBe(project.assets[0].id)
    expect(project.pages[0].slots[1].assetId).toBe(project.assets[0].id)
  })

  it('restores v2 slots without dropping placed images or crop settings', () => {
    const project = normalizeLegacyDraft({
      version: 2,
      assets: [{ id: 'asset-v2', src: '/assets/original.png', originalSrc: '/assets/original.png' }],
      pages: [{
        rows: 3,
        columns: 2,
        slots: [{
          id: 'slot-v2',
          assetId: 'asset-v2',
          src: '/assets/original.png',
          originalSrc: '/assets/original.png',
          note: '保留这条说明',
          cropX: 0.2,
          cropY: 0.8,
          zoom: 1.45,
        }],
      }],
    })

    expect(project.pages[0].slots[0]).toMatchObject({
      id: 'slot-v2',
      assetId: 'asset-v2',
      src: '/assets/original.png',
      note: '保留这条说明',
      cropX: 0.2,
      cropY: 0.8,
      zoom: 1.45,
    })
  })
})
