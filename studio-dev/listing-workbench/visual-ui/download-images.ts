import type { PlanImage } from './types';

export async function downloadImages(
  images: PlanImage[], deliverable: 'gallery' | 'aplus', reviewed: boolean, prefix = 'listing',
) {
  const { default: JSZip } = await import('jszip');
  const zip = new JSZip();
  for (const [index, image] of images.entries()) {
    const response = await fetch(image.final_url!, { credentials: 'include' });
    if (!response.ok) throw new Error(`第 ${index + 1} 张下载失败`);
    const blob = await response.blob();
    const extension = blob.type.includes('jpeg') ? 'jpg' : blob.type.includes('webp') ? 'webp' : 'png';
    const role = String(image.role || image.slot).replace(/[\\/:*?"<>|]/g, '-');
    const draft = image.human_reviewed ? '' : '_DRAFT';
    zip.file(`${String(index + 1).padStart(2, '0')}_${role}${draft}.${extension}`, blob);
  }
  zip.file('review-manifest.json', JSON.stringify({
    deliverable,
    exported_at: new Date().toISOString(),
    commercially_reviewed: reviewed,
    images: images.map((image, index) => ({
      order: index + 1, slot: image.slot, role: image.role,
      human_reviewed: !!image.human_reviewed, evidence: image.evidence || '',
    })),
  }, null, 2));
  const url = URL.createObjectURL(await zip.generateAsync({ type: 'blob' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `${prefix.replace(/[\\/:*?"<>|]/g, '-')}_${deliverable}_${reviewed ? 'reviewed' : 'draft'}.zip`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
