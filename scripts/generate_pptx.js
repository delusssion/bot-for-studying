#!/usr/bin/env node
'use strict';

const PptxGenJS = require('pptxgenjs');
const fs = require('fs');

// ─── Color schemes ────────────────────────────────────────────────────────────

const SCHEMES = {
  blue: {
    bg: '1E3A5F', bgLight: 'F0F4F8',
    accent: '2E75B6', accent2: 'E8F1FA',
    title: 'FFFFFF', text: '1A1A2E',
    header: '1E3A5F', headerText: 'FFFFFF',
  },
  green: {
    bg: '1E4620', bgLight: 'F0F7F0',
    accent: '2E7D32', accent2: 'E8F5E9',
    title: 'FFFFFF', text: '1A2E1A',
    header: '1E4620', headerText: 'FFFFFF',
  },
  dark: {
    bg: '0D1117', bgLight: '161B22',
    accent: '58A6FF', accent2: '21262D',
    title: 'FFFFFF', text: 'C9D1D9',
    header: '161B22', headerText: '58A6FF',
  },
  minimal: {
    bg: '212121', bgLight: 'FAFAFA',
    accent: '424242', accent2: 'F5F5F5',
    title: 'FFFFFF', text: '212121',
    header: 'FAFAFA', headerText: '212121',
  },
};

const W = 13.33; // LAYOUT_WIDE width, inches
const H = 7.5;
const MARGIN = 0.4;
const HDR_H = 1.2;

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getScheme(data) {
  const custom = data.custom_colors;
  if (custom && typeof custom === 'object') {
    const c = (s, d) => ((s || d) + '').replace(/^#/, '').toUpperCase().padEnd(6, '0');
    return {
      bg:         c(custom.bg || custom.background, '1E3A5F'),
      bgLight:    c(custom.bgLight, 'F0F4F8'),
      accent:     c(custom.accent, '2E75B6'),
      accent2:    c(custom.accent2, 'E8F1FA'),
      title:      c(custom.title, 'FFFFFF'),
      text:       c(custom.text, '1A1A2E'),
      header:     c(custom.header || custom.bg || custom.background, '1E3A5F'),
      headerText: c(custom.headerText, 'FFFFFF'),
    };
  }
  return SCHEMES[data.color_scheme] || SCHEMES.blue;
}

/** Blend fg over bg at opacity (0–1). Returns 6-char hex. */
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

function noLine() { return { type: 'none' }; }

function addSlideNumber(slide, num) {
  slide.addText(String(num), {
    x: W - 0.85, y: H - 0.38, w: 0.65, h: 0.28,
    fontSize: 11, color: '9E9E9E',
    fontFace: 'Calibri', align: 'right',
  });
}

function addHeaderBar(slide, title, sc) {
  slide.addShape('rect', {
    x: 0, y: 0, w: W, h: HDR_H,
    fill: { color: sc.header }, line: noLine(),
  });
  slide.addText(title, {
    x: MARGIN, y: 0, w: W - MARGIN * 2, h: HDR_H,
    fontSize: 28, bold: true,
    color: sc.headerText, fontFace: 'Calibri',
    valign: 'middle', wrap: true,
  });
}

/** Renders bullet-style blocks. Returns next free Y. */
function addBulletBlocks(slide, items, sc, startY, maxH) {
  const BLOCK_H  = 0.56;
  const BLOCK_GAP = 0.12;
  const STRIP_W  = 0.08;
  const BLOCK_W  = W - MARGIN * 2;
  const maxCount = Math.max(1, Math.floor((maxH + BLOCK_GAP) / (BLOCK_H + BLOCK_GAP)));
  const visible  = items.slice(0, maxCount);

  visible.forEach((item, i) => {
    const y = startY + i * (BLOCK_H + BLOCK_GAP);
    slide.addShape('roundRect', {
      x: MARGIN, y, w: BLOCK_W, h: BLOCK_H,
      fill: { color: sc.accent2 }, line: noLine(), rectRadius: 0.1,
    });
    slide.addShape('rect', {
      x: MARGIN, y, w: STRIP_W, h: BLOCK_H,
      fill: { color: sc.accent }, line: noLine(),
    });
    slide.addText(String(item), {
      x: MARGIN + STRIP_W + 0.14, y: y + 0.05,
      w: BLOCK_W - STRIP_W - 0.22, h: BLOCK_H - 0.1,
      fontSize: 16, color: sc.text,
      fontFace: 'Calibri', valign: 'middle', wrap: true,
    });
  });

  if (items.length > maxCount) {
    const overY = startY + maxCount * (BLOCK_H + BLOCK_GAP);
    slide.addText(`… и ещё ${items.length - maxCount} пункт(а)`, {
      x: MARGIN, y: overY, w: 5, h: 0.28,
      fontSize: 11, color: '9E9E9E',
      fontFace: 'Calibri', italic: true,
    });
  }
}

// ─── Slide builders ──────────────────────────────────────────────────────────

function buildTitleSlide(pptx, sd, sc, num) {
  const slide = pptx.addSlide();
  slide.background = { fill: sc.bg };

  // Decorative ghost number — blended at 15% opacity
  const decoColor = blend(sc.bg, 'FFFFFF', 0.15);
  slide.addText(String(num).padStart(2, '0'), {
    x: W * 0.52, y: -1,
    w: W * 0.48, h: H + 2,
    fontSize: 270, bold: true,
    color: decoColor, fontFace: 'Calibri',
    align: 'center', valign: 'middle',
  });

  // Main title
  slide.addText(sd.title || '', {
    x: MARGIN, y: H * 0.18,
    w: W * 0.62, h: H * 0.42,
    fontSize: 44, bold: true,
    color: sc.title, fontFace: 'Calibri',
    align: 'left', valign: 'middle',
    wrap: true,
  });

  // Subtitle
  const subtitle = sd.subtitle || sd.notes || '';
  if (subtitle) {
    slide.addText(subtitle, {
      x: MARGIN, y: H * 0.62,
      w: W * 0.62, h: 0.9,
      fontSize: 22, color: sc.accent,
      fontFace: 'Calibri', align: 'left',
      valign: 'top', wrap: true,
    });
    // Short accent line under subtitle
    slide.addShape('rect', {
      x: MARGIN, y: H * 0.62 + 0.96,
      w: W * 0.20, h: 0.04,
      fill: { color: sc.accent }, line: noLine(),
    });
  }

  // Bottom-left caption
  slide.addText('SmartUchenik', {
    x: MARGIN, y: H - 0.44,
    w: 2.5, h: 0.28,
    fontSize: 11, color: '888888',
    fontFace: 'Calibri',
  });

  addSlideNumber(slide, num);
}

function buildContentSlide(pptx, sd, sc, num) {
  const slide = pptx.addSlide();
  slide.background = { fill: sc.bgLight };
  addHeaderBar(slide, sd.title || '', sc);

  const items  = sd.content || [];
  const startY = HDR_H + 0.2;
  addBulletBlocks(slide, items, sc, startY, H - startY - 0.38);

  addSlideNumber(slide, num);
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

  const GAP    = 0.12;
  const colW   = (W - MARGIN * 2 - GAP) / 2;
  const STRIP  = 0.06;
  const BH     = 0.50;
  const BG     = 0.10;
  const startY = HDR_H + 0.2;
  let   colY   = startY;

  const lh = sd.left_column_title  || '';
  const rh = sd.right_column_title || '';
  if (lh) {
    slide.addText(lh, {
      x: MARGIN, y: colY, w: colW, h: 0.32,
      fontSize: 14, bold: true,
      color: sc.accent, fontFace: 'Calibri',
    });
  }
  if (rh) {
    slide.addText(rh, {
      x: MARGIN + colW + GAP, y: colY, w: colW, h: 0.32,
      fontSize: 14, bold: true,
      color: sc.accent, fontFace: 'Calibri',
    });
  }
  if (lh || rh) colY += 0.36;

  const maxItems = Math.max(1, Math.floor((H - colY - 0.32 + BG) / (BH + BG)));

  const drawItems = (items, rx) => {
    items.slice(0, maxItems).forEach((item, i) => {
      const y = colY + i * (BH + BG);
      slide.addShape('roundRect', {
        x: rx, y, w: colW, h: BH,
        fill: { color: sc.accent2 }, line: noLine(), rectRadius: 0.1,
      });
      slide.addShape('rect', {
        x: rx, y, w: STRIP, h: BH,
        fill: { color: sc.accent }, line: noLine(),
      });
      slide.addText(String(item), {
        x: rx + STRIP + 0.1, y: y + 0.04,
        w: colW - STRIP - 0.15, h: BH - 0.08,
        fontSize: 14, color: sc.text,
        fontFace: 'Calibri', valign: 'middle', wrap: true,
      });
    });
  };

  drawItems(left, MARGIN);

  // Divider
  slide.addShape('rect', {
    x: MARGIN + colW + GAP / 2 - 0.01, y: startY,
    w: 0.02, h: H - startY - 0.32,
    fill: { color: sc.accent }, line: noLine(),
  });

  drawItems(right, MARGIN + colW + GAP);

  addSlideNumber(slide, num);
}

function buildSectionHeaderSlide(pptx, sd, sc, num) {
  const slide = pptx.addSlide();
  slide.background = { fill: sc.bg };

  slide.addText(sd.title || '', {
    x: MARGIN, y: H * 0.24,
    w: W - MARGIN * 2, h: H * 0.46,
    fontSize: 36, bold: true,
    color: sc.title, fontFace: 'Calibri',
    align: 'center', valign: 'middle', wrap: true,
  });

  // Centered accent line (30% width) below title
  const lineW = W * 0.30;
  slide.addShape('rect', {
    x: (W - lineW) / 2, y: H * 0.24 + H * 0.46 + 0.18,
    w: lineW, h: 0.06,
    fill: { color: sc.accent }, line: noLine(),
  });

  addSlideNumber(slide, num);
}

function buildConclusionSlide(pptx, sd, sc, num) {
  const slide = pptx.addSlide();
  slide.background = { fill: sc.bgLight };
  addHeaderBar(slide, sd.title || '', sc);

  const FOOTER_H = 0.6;
  const startY   = HDR_H + 0.2;
  const maxH     = H - startY - FOOTER_H - 0.18;
  addBulletBlocks(slide, sd.content || [], sc, startY, maxH);

  // Footer bar
  const footerY = H - FOOTER_H;
  slide.addShape('rect', {
    x: 0, y: footerY, w: W, h: FOOTER_H,
    fill: { color: sc.bg }, line: noLine(),
  });
  slide.addText('Спасибо за внимание!', {
    x: 0, y: footerY, w: W, h: FOOTER_H,
    fontSize: 18, bold: true, color: 'FFFFFF',
    fontFace: 'Calibri', align: 'center', valign: 'middle',
  });

  addSlideNumber(slide, num);
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
