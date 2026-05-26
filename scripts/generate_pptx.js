#!/usr/bin/env node
'use strict';

const PptxGenJS = require('pptxgenjs');
const fs = require('fs');

// ─── Color schemes ────────────────────────────────────────────────────────────

const SCHEMES = {
  blue: {
    bg: '1E3A5F', bgLight: 'F0F4F8',
    accent: '2E75B6', accent2: 'D6E4F0',
    titleText: 'FFFFFF', text: '1A1A2E',
    headerBg: '1E3A5F', headerText: 'FFFFFF',
    mutedText: '6B7280',
  },
  green: {
    bg: '1B4332', bgLight: 'F0F7F0',
    accent: '2D6A4F', accent2: 'D8F3DC',
    titleText: 'FFFFFF', text: '1A2E1A',
    headerBg: '1B4332', headerText: 'FFFFFF',
    mutedText: '6B7280',
  },
  dark: {
    bg: '0D1117', bgLight: '161B22',
    accent: '58A6FF', accent2: '21262D',
    titleText: 'FFFFFF', text: 'C9D1D9',
    headerBg: '21262D', headerText: '58A6FF',
    mutedText: '8B949E',
  },
  minimal: {
    bg: '212121', bgLight: 'FFFFFF',
    accent: '212121', accent2: 'F5F5F5',
    titleText: 'FFFFFF', text: '212121',
    headerBg: '212121', headerText: 'FFFFFF',
    mutedText: '9E9E9E',
  },
};

const W      = 13.33;  // LAYOUT_WIDE width, inches
const H      = 7.5;
const MARGIN = 0.4;
const HDR_W  = 10.0;   // header/footer strip width (intentional cutoff design)
const HDR_H  = 1.1;

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getScheme(data) {
  const custom = data.custom_colors;
  if (custom && typeof custom === 'object') {
    const c = (s, d) => ((s || d) + '').replace(/^#/, '').toUpperCase();
    return {
      bg:         c(custom.bg || custom.background,          '1E3A5F'),
      bgLight:    c(custom.bgLight,                          'F0F4F8'),
      accent:     c(custom.accent,                           '2E75B6'),
      accent2:    c(custom.accent2,                          'D6E4F0'),
      titleText:  c(custom.titleText || custom.title,        'FFFFFF'),
      text:       c(custom.text,                             '1A1A2E'),
      headerBg:   c(custom.headerBg || custom.header || custom.bg, '1E3A5F'),
      headerText: c(custom.headerText,                       'FFFFFF'),
      mutedText:  c(custom.mutedText,                        '6B7280'),
    };
  }
  return SCHEMES[data.color_scheme] || SCHEMES.blue;
}

/** Blend fg over bg at opacity 0–1, returns 6-char hex. */
function blend(bgHex, fgHex, opacity) {
  const p = h => [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16));
  const [br, bg, bb] = p(bgHex);
  const [fr, fg, fb] = p(fgHex);
  return [br, bg, bb]
    .map((b, i) => Math.round(b * (1 - opacity) + [fr, fg, fb][i] * opacity))
    .map(v => v.toString(16).padStart(2, '0'))
    .join('')
    .toUpperCase();
}

const noLine = () => ({ type: 'none' });

function addSlideNumber(slide, num, sc) {
  slide.addText(String(num), {
    x: W - 0.8, y: H - 0.38, w: 0.6, h: 0.28,
    fontSize: 10, color: sc.mutedText,
    fontFace: 'Calibri', align: 'right',
  });
}

function addHeaderBar(slide, title, sc) {
  slide.addShape('rect', {
    x: 0, y: 0, w: HDR_W, h: HDR_H,
    fill: { color: sc.headerBg }, line: noLine(),
  });
  slide.addText(title, {
    x: MARGIN, y: 0, w: HDR_W - MARGIN - 0.15, h: HDR_H,
    fontSize: 26, bold: true,
    color: sc.headerText, fontFace: 'Calibri',
    valign: 'middle', wrap: true,
  });
}

/**
 * Estimate block height from text length.
 * blockW: usable text width in inches.
 */
function calcBlockH(text, fontSize, blockW) {
  const charsPerLine = Math.max(1, Math.floor(blockW * 10.5 / fontSize));
  const lines = Math.ceil(text.length / charsPerLine);
  const lineH = fontSize * 0.0185;
  return Math.max(0.48, lines * lineH + 0.22);
}

/**
 * Render bullet blocks starting at (x, startY).
 * Returns final Y position after last block.
 */
function drawBulletBlocks(slide, items, sc, x, startY, blockW, maxH, fontSize) {
  const STRIP_W   = 0.07;
  const BLOCK_GAP = 0.1;
  let y = startY;

  for (const item of items) {
    const text = String(item);
    const bh   = calcBlockH(text, fontSize, blockW - STRIP_W - 0.27);

    if (y + bh > startY + maxH) break;

    slide.addShape('roundRect', {
      x, y, w: blockW, h: bh,
      fill: { color: sc.accent2 }, line: noLine(), rectRadius: 0.08,
    });
    slide.addShape('rect', {
      x, y, w: STRIP_W, h: bh,
      fill: { color: sc.accent }, line: noLine(),
    });
    slide.addText(text, {
      x: x + STRIP_W + 0.15, y: y + 0.05,
      w: blockW - STRIP_W - 0.22, h: bh - 0.1,
      fontSize, color: sc.text,
      fontFace: 'Calibri', valign: 'middle', wrap: true,
    });
    y += bh + BLOCK_GAP;
  }
  return y;
}

// ─── Slide builders ──────────────────────────────────────────────────────────

function buildTitleSlide(pptx, sd, sc, num) {
  const slide = pptx.addSlide();
  slide.background = { fill: sc.bg };

  // Ghost decorative number (15% opacity)
  const decoColor = blend(sc.bg, 'FFFFFF', 0.15);
  slide.addText(String(num).padStart(2, '0'), {
    x: W * 0.58, y: -0.8,
    w: W * 0.42, h: H + 1.6,
    fontSize: 200, bold: true,
    color: decoColor, fontFace: 'Calibri',
    align: 'center', valign: 'middle',
  });

  // Main title — centered
  slide.addText(sd.title || '', {
    x: MARGIN, y: H * 0.14,
    w: W - MARGIN * 2, h: H * 0.44,
    fontSize: 44, bold: true,
    color: sc.titleText, fontFace: 'Calibri',
    align: 'center', valign: 'middle', wrap: true,
  });

  // Subtitle
  const subtitle = sd.subtitle || sd.notes || '';
  if (subtitle) {
    slide.addText(subtitle, {
      x: MARGIN, y: H * 0.60,
      w: W - MARGIN * 2, h: 0.9,
      fontSize: 22, color: sc.accent,
      fontFace: 'Calibri', align: 'center',
      valign: 'top', wrap: true,
    });
  }

  // Accent line left (25% width)
  slide.addShape('rect', {
    x: MARGIN, y: H * 0.60 + (subtitle ? 0.96 : 0),
    w: W * 0.25, h: 0.04,
    fill: { color: sc.accent }, line: noLine(),
  });

  // Bottom-left muted caption
  slide.addText('SmartUchenik', {
    x: MARGIN, y: H - 0.42,
    w: 2.4, h: 0.28,
    fontSize: 11, color: sc.mutedText, fontFace: 'Calibri',
  });

  addSlideNumber(slide, num, sc);
}

function buildContentSlide(pptx, sd, sc, num) {
  const slide = pptx.addSlide();
  slide.background = { fill: sc.bgLight };
  addHeaderBar(slide, sd.title || '', sc);

  const startY = HDR_H + 0.18;
  const blockW = W - MARGIN * 2;
  drawBulletBlocks(slide, sd.content || [], sc, MARGIN, startY, blockW, H - startY - 0.35, 15);

  addSlideNumber(slide, num, sc);
}

function buildTwoColumnSlide(pptx, sd, sc, num) {
  let left  = sd.left_column  || [];
  let right = sd.right_column || [];

  if (!left.length && !right.length) {
    const all = sd.content || [];
    const mid = Math.ceil(all.length / 2);
    left  = all.slice(0, mid);
    right = all.slice(mid);
  }
  if (!left.length && !right.length) {
    buildContentSlide(pptx, sd, sc, num);
    return;
  }

  const slide = pptx.addSlide();
  slide.background = { fill: sc.bgLight };
  addHeaderBar(slide, sd.title || '', sc);

  const GAP    = 0.2;
  const colW   = (W - MARGIN * 2 - GAP) / 2;
  const startY = HDR_H + 0.18;
  const colH   = H - startY - 0.35;
  let   colY   = startY;

  const lh = sd.left_column_title  || '';
  const rh = sd.right_column_title || '';
  if (lh) {
    slide.addText(lh, {
      x: MARGIN, y: colY, w: colW, h: 0.3,
      fontSize: 14, bold: true, color: sc.accent, fontFace: 'Calibri',
    });
  }
  if (rh) {
    slide.addText(rh, {
      x: MARGIN + colW + GAP, y: colY, w: colW, h: 0.3,
      fontSize: 14, bold: true, color: sc.accent, fontFace: 'Calibri',
    });
  }
  if (lh || rh) colY += 0.34;

  // Divider line
  slide.addShape('rect', {
    x: MARGIN + colW + GAP / 2 - 0.01, y: startY,
    w: 0.02, h: colH,
    fill: { color: sc.accent }, line: noLine(),
  });

  drawBulletBlocks(slide, left,  sc, MARGIN,               colY, colW, H - colY - 0.35, 13);
  drawBulletBlocks(slide, right, sc, MARGIN + colW + GAP,  colY, colW, H - colY - 0.35, 13);

  addSlideNumber(slide, num, sc);
}

function buildSectionHeaderSlide(pptx, sd, sc, num) {
  const slide = pptx.addSlide();
  slide.background = { fill: sc.bg };

  slide.addText(sd.title || '', {
    x: MARGIN, y: 0,
    w: W - MARGIN * 2, h: H,
    fontSize: 38, bold: true,
    color: sc.titleText, fontFace: 'Calibri',
    align: 'center', valign: 'middle', wrap: true,
  });

  // Centered accent line (20% width)
  const lineW = W * 0.20;
  slide.addShape('rect', {
    x: (W - lineW) / 2, y: H * 0.64,
    w: lineW, h: 0.04,
    fill: { color: sc.accent }, line: noLine(),
  });

  addSlideNumber(slide, num, sc);
}

function buildConclusionSlide(pptx, sd, sc, num) {
  const slide = pptx.addSlide();
  slide.background = { fill: sc.bgLight };
  addHeaderBar(slide, sd.title || '', sc);

  const FOOTER_H = 0.7;
  const startY   = HDR_H + 0.18;
  const blockW   = W - MARGIN * 2;
  drawBulletBlocks(slide, sd.content || [], sc, MARGIN, startY, blockW, H - startY - FOOTER_H - 0.18, 15);

  // Footer strip (10" wide, headerBg color)
  const footerY = H - FOOTER_H;
  slide.addShape('rect', {
    x: 0, y: footerY, w: HDR_W, h: FOOTER_H,
    fill: { color: sc.headerBg }, line: noLine(),
  });
  slide.addText('Спасибо за внимание!', {
    x: 0, y: footerY, w: HDR_W, h: FOOTER_H,
    fontSize: 18, bold: true, color: sc.titleText,
    fontFace: 'Calibri', align: 'center', valign: 'middle',
  });

  addSlideNumber(slide, num, sc);
}

// ─── Dispatch ─────────────────────────────────────────────────────────────────

const BUILDERS = {
  title:          buildTitleSlide,
  content:        buildContentSlide,
  two_column:     buildTwoColumnSlide,
  section_header: buildSectionHeaderSlide,
  conclusion:     buildConclusionSlide,
  image_text:     buildContentSlide,
};

// ─── Entry point ──────────────────────────────────────────────────────────────

async function main() {
  const [jsonPath, outputPath] = process.argv.slice(2);
  if (!jsonPath || !outputPath) {
    process.stderr.write('Usage: node generate_pptx.js <input.json> <output.pptx>\n');
    process.exit(1);
  }

  const data = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
  const sc   = getScheme(data);

  const pptx = new PptxGenJS();
  pptx.layout = 'LAYOUT_WIDE';

  let slides = data.slides || [];
  if (!slides.length) {
    slides = [{ layout: 'title', title: data.title || 'Презентация', subtitle: '' }];
  }

  slides.forEach((sd, i) => {
    const builder = BUILDERS[sd.layout || 'content'] || buildContentSlide;
    try {
      builder(pptx, sd, sc, i + 1);
    } catch (err) {
      process.stderr.write(`Slide ${i + 1} (${sd.layout}): ${err.message}\n`);
      buildContentSlide(pptx, sd, sc, i + 1);
    }
  });

  const buf = await pptx.write({ outputType: 'nodebuffer' });
  fs.writeFileSync(outputPath, buf);
  process.stdout.write(`OK: ${outputPath}\n`);
}

main().catch(err => {
  process.stderr.write(`Fatal: ${err.message}\n${err.stack}\n`);
  process.exit(1);
});
